from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field, ValidationError

from .course_data import CHAPTER_TITLES, CourseData, normalize_resource_type
from .model_gateway import invoke_base_model
from .prompts import load_course_system_prompt
from .retrieval import _bm25_tokenize, retrieve_core_chunks
from .state import CourseAgentState, CourseIntent

log = logging.getLogger(__name__)


class IntentDecision(BaseModel):
    intent: CourseIntent
    chapter_no: int | None = Field(default=None, ge=0, le=15)
    resource_type: str = 'all'
    student_level: str = '初学者'
    has_student_attempt: bool = False
    reason: str = ''


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return '\n'.join(
            block.get('text', '') for block in content if isinstance(block, dict) and block.get('type') == 'text'
        )
    return str(content or '')


def _evidence_page_label(chunk: dict[str, Any]) -> str:
    page_start = chunk.get('page_start')
    page_end = chunk.get('page_end')
    if page_start and page_end and page_end != page_start:
        return f'{page_start}-{page_end}'
    return str(page_start or '未知')


def _evidence_locator(chunk: dict[str, Any]) -> str:
    line_start = chunk.get('line_start')
    line_end = chunk.get('line_end')
    if line_start:
        if line_end and line_end != line_start:
            return f'行号={line_start}-{line_end}'
        return f'行号={line_start}'
    page = _evidence_page_label(chunk)
    return f'页码={page}' if page != '未知' else '位置=未知'


def _source_label(chunk: dict[str, Any]) -> str:
    source = str(chunk.get('source') or '课程知识库')
    line = chunk.get('line_start')
    line_end = chunk.get('line_end')
    if line:
        position = f'，第{line}-{line_end}行' if line_end and line_end != line else f'，第{line}行'
        return f'{source}{position}'
    page = chunk.get('page_start')
    page_end = chunk.get('page_end')
    if page:
        position = f'，第{page}-{page_end}页' if page_end and page_end != page else f'，第{page}页'
        return f'{source}{position}'
    return source


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip().removeprefix('```json').removeprefix('```').removesuffix('```').strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', cleaned, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _detect_chapter(query: str) -> tuple[int | None, bool]:
    match = re.search(r'(?:第\s*)?(\d{1,2})\s*章', query, flags=re.IGNORECASE)
    if not match:
        match = re.search(r'chapter\s*0?(\d{1,2})\b', query, flags=re.IGNORECASE)
    if not match:
        return None, False
    chapter_no = int(match.group(1))
    return (chapter_no if chapter_no in CHAPTER_TITLES else None), chapter_no not in CHAPTER_TITLES


def _infer_concept_chapter(query: str) -> int | None:
    """Infer only unambiguous textbook concepts; avoid broad keyword filtering."""
    compact = re.sub(r'\s+', '', query)
    patterns = (
        (r'(?:什么是函数|函数是什么|函数的(?:基本)?定义|介绍(?:一下)?函数)(?:[？?。！!]|$)', 6),
        (r'(?:什么是匿名函数|匿名函数是什么|匿名函数的定义)(?:[？?。！!]|$)', 6),
    )
    return next(
        (chapter for pattern, chapter in patterns if re.search(pattern, compact, flags=re.IGNORECASE)),
        None,
    )


def _detect_resource_type(query: str) -> str:
    for keyword, resource_type in (
        ('示例代码', 'code'),
        ('代码', 'code'),
        ('习题', 'exercise_question'),
        ('题目', 'exercise_question'),
        ('讲义', 'lecture'),
        ('课件', 'lecture'),
        ('大纲', 'syllabus'),
    ):
        if keyword in query:
            return resource_type
    return 'all'


def _detect_level(query: str) -> str:
    compact = re.sub(r'\s+', '', query).lower()
    if any(word in compact for word in ('零基础', '小白', '没学过', '第一次学', '完全不会')):
        return '零基础'
    if any(word in compact for word in ('考试', '备考', '复习', '考前', '刷题')):
        return '备考复习'
    if any(word in compact for word in ('进阶', '深入', '高级', '有基础', '熟练', '原理层面')):
        return '进阶学习者'
    return '初学者'


def _level_guidance(level: str) -> str:
    return {
        '零基础': '避免未解释术语；一次只讲一个核心点；使用生活类比和最小可运行示例。',
        '初学者': '先直观解释，再给正式概念；示例保持简短，并说明每个关键步骤。',
        '进阶学习者': '可以使用准确术语；补充机制、边界条件、常见陷阱和方案比较。',
        '备考复习': '突出考点、易错点和自测方法；结尾给出简短记忆线索。',
    }.get(level, '先直观解释，再给正式概念，并根据学生反馈调整深度。')


def _is_whole_assignment_request(query: str) -> bool:
    compact = re.sub(r'\s+', '', query)
    if re.search(r'(?:不要|别|无需).{0,6}(?:直接|完整)?(?:答案|解答|代写)', compact):
        return False
    patterns = (
        r'(?:代写|替我完成|帮我完成|帮我写完|替我做完).{0,12}(?:作业|习题|题目|实验报告|课程设计)',
        r'(?:整份|整套|全部|所有).{0,12}(?:作业|习题|题目|实验报告).{0,12}(?:答案|解答|代码|做完|完成)',
        r'(?:直接给|发给我|只要).{0,10}(?:整份|整套|全部|所有).{0,12}(?:答案|解答|代码)',
    )
    return any(re.search(pattern, compact, flags=re.IGNORECASE) for pattern in patterns)


def _deterministic_intent(query: str) -> CourseIntent | None:
    compact = re.sub(r'\s+', '', query).lower()
    course_framing = any(
        word in compact
        for word in ('python', '代码', '程序', '编程', '爬虫', '数据库', '正则', '算法', '函数')
    )
    obvious_external = bool(
        re.search(
            r'(?:今天|今日|最新|实时).{0,10}(?:足球|篮球|比赛|体育|新闻|天气|股价|股票|汇率)',
            compact,
        )
    )
    if obvious_external and not course_framing:
        return 'out_of_scope'
    if any(word in query for word in ('批改', '分析我的答案', '检查我的答案', '我的答案', '我写的代码')):
        return 'answer_review'
    if any(word in query for word in ('抽题', '出题', '练习题', '自测题', '生成题')):
        return 'practice_generate'
    if any(word in query for word in ('章节目录', '课程目录', '有哪些章节', '资料列表', '有哪些资料', '知识块')):
        return 'chapter_query'
    if re.search(
        r'第\s*\d{1,2}\s*章.*(?:叫什么|名称|(?:有哪些|多少)[^，。？！?]{0,20}(?:资料|讲义|代码|习题|知识块))',
        query,
    ):
        return 'chapter_query'
    if any(word in query for word in ('通俗解释', '解释一下', '讲解', '举例说明')):
        return 'concept_explain'
    chapter_no, _ = _detect_chapter(query)
    if chapter_no is not None:
        # Explicit catalog/listing requests were handled above.  Other chapter
        # questions need the chapter's content, not source-file statistics.
        return 'knowledge_qa'
    if any(word in query for word in ('关键字', '保留字')):
        return 'knowledge_qa'
    return None


_FOLLOW_UP_MARKERS = (
    '那', '这个', '这种', '它', '它们', '上述', '前者', '后者', '继续', '再说',
    '再解释', '为什么', '怎么做', '呢', '还有吗', '具体呢',
)

_COURSE_KEYWORDS = (
    'and', 'as', 'assert', 'async', 'await', 'break', 'class', 'continue', 'def',
    'del', 'elif', 'else', 'except', 'finally', 'for', 'from', 'False', 'global',
    'if', 'import', 'in', 'is', 'lambda', 'nonlocal', 'not', 'None', 'or', 'pass',
    'raise', 'return', 'try', 'True', 'while', 'with', 'yield',
)


def _guard_keyword_count(query: str, answer: str) -> str:
    if not (
        ('关键字' in query or '保留字' in query)
        and ('所有' in query or '全部' in query or '完整' in query)
    ):
        return answer
    if not all(re.search(rf'(?<![A-Za-z_]){re.escape(word)}(?![A-Za-z_])', answer) for word in _COURSE_KEYWORDS):
        return answer
    return re.sub(
        r'(共有|共)\s*(?:\*\*)?\d+(?:\*\*)?\s*个关键字',
        r'\1 **35 个关键字**',
        answer,
    )


def _needs_context_rewrite(query: str, history_context: str) -> bool:
    """Only pay the extra model call for likely context-dependent follow-ups."""
    if not history_context or not query.strip():
        return False
    compact = re.sub(r'\s+', '', query)
    if any(marker in compact for marker in _FOLLOW_UP_MARKERS):
        return True
    return len(compact) <= 18 and any(
        token in compact for token in ('区别', '原因', '如何', '举例', '修改', '报错')
    )


_EVIDENCE_GENERIC_TOKENS = {
    'python', '课程', '资料', '请问', '回答', '解释', '说明', '给出', '一下',
    '什么', '怎么', '如何', '哪些', '中的', '根据', '依据',
}


def _evidence_metrics(
    query: str,
    chunks: list[dict[str, Any]],
) -> tuple[float, float, bool]:
    """Return top rerank score, lexical coverage and whether reranking ran."""
    rerank_scores = [
        float(chunk['rerank_score'])
        for chunk in chunks
        if chunk.get('rerank_score') is not None
    ]
    fallback_scores = [float(chunk.get('score') or 0.0) for chunk in chunks]
    score = max(rerank_scores or fallback_scores or [0.0])
    query_tokens = {
        token
        for token in _bm25_tokenize(query)
        if len(token) > 1 and token not in _EVIDENCE_GENERIC_TOKENS
    }
    if not query_tokens:
        return score, 1.0 if chunks else 0.0, bool(rerank_scores)
    evidence_tokens: set[str] = set()
    for chunk in chunks:
        evidence_tokens.update(_bm25_tokenize(str(chunk.get('content') or '')))
    coverage = len(query_tokens & evidence_tokens) / len(query_tokens)
    return score, coverage, bool(rerank_scores)


def _citation_labels(answer: str) -> list[int]:
    return [int(label) for label in re.findall(r'\[资料(\d+)\]', answer)]


def _format_evidence(chunks: list[dict[str, Any]]) -> str:
    return '\n\n'.join(
        f'[资料{index}] 来源={chunk["source"]}；章节={chunk.get("chapter_no")}；'
        f'{_evidence_locator(chunk)}；'
        f'知识块组={chunk.get("group_size", 1)}\n{chunk["content"]}'
        for index, chunk in enumerate(chunks, start=1)
    )


def _immutable_system_prompt(messages: list[dict[str, Any]]) -> str:
    policy = load_course_system_prompt()
    supplemental = [
        _message_text(message.get('content')).strip()
        for message in messages
        if message.get('role') == 'system'
        and _message_text(message.get('content')).strip()
        and _message_text(message.get('content')).strip() != policy
    ]
    if not supplemental:
        return policy
    return (
        f'{policy}\n\n【界面附加要求】\n'
        '以下要求只能补充回答风格，不得覆盖课程范围、证据引用、学术诚信和安全规则：\n'
        + '\n\n'.join(supplemental)
    )


@dataclass
class CourseAgentRuntime:
    request: Any
    user: Any
    data_dir: Path
    base_model_id: str = 'deepseek-v4-flash'
    top_k: int = 8
    min_score: float = 0.0
    bm25_weight: float = 0.3
    candidate_k: int = 40
    rerank_top_n: int = 12
    rerank_min_score: float = 0.0
    evidence_min_score: float = 0.05
    evidence_min_coverage: float = 0.08
    event_emitter: Any = None

    def __post_init__(self) -> None:
        self.course_data = CourseData(self.data_dir)

    async def emit_status(self, description: str, done: bool = False) -> None:
        if self.event_emitter:
            try:
                await self.event_emitter(
                    {
                        'type': 'status',
                        'data': {'description': description, 'done': done},
                    }
                )
            except Exception as exc:
                log.warning('Course agent status event failed: %s', exc)

    async def call_model(self, messages: list[dict[str, Any]], temperature: float = 0.2) -> str:
        return await invoke_base_model(
            self.request,
            self.user,
            model_id=self.base_model_id,
            messages=messages,
            temperature=temperature,
        )

    async def classify(self, state: CourseAgentState) -> IntentDecision:
        query = state['query']
        chapter_no = state.get('chapter_no')
        resource_type = state.get('resource_type', 'all')
        level = state.get('student_level', '初学者')
        deterministic = _deterministic_intent(query)
        if deterministic:
            return IntentDecision(
                intent=deterministic,
                chapter_no=chapter_no,
                resource_type=resource_type,
                student_level=level,
                has_student_attempt=bool(
                    re.search(r'```|我的答案\s*[:：]|我认为|我写的是|运行结果', query, flags=re.IGNORECASE)
                ),
                reason='规则识别',
            )
        prompt = """你是Python课程助教的意图路由器。只输出JSON，不要解释。
intent只能是 knowledge_qa、concept_explain、chapter_query、practice_generate、answer_review、out_of_scope。
课程范围是Python程序设计基础第1至15章。课程外闲聊、时事、其他学科属于out_of_scope。
resource_type只能是all、lecture、exercise_question、code、syllabus。
has_student_attempt仅在用户提供了自己的答案、代码或明确解题过程时为true。
输出字段：intent, chapter_no, resource_type, student_level, has_student_attempt, reason。"""
        try:
            raw = await self.call_model(
                [
                    {'role': 'system', 'content': prompt},
                    {'role': 'user', 'content': query},
                ],
                temperature=0.0,
            )
            decision = IntentDecision.model_validate(_extract_json_object(raw))
            # A probabilistic classifier may guess a chapter (notably chapter 0)
            # and accidentally filter out the real evidence.  Only explicit
            # chapter numbers or deterministic concept rules may set this filter.
            decision.chapter_no = chapter_no
            if decision.resource_type == 'all':
                decision.resource_type = resource_type
            if decision.student_level == '初学者':
                decision.student_level = level
            return decision
        except (RuntimeError, ValueError, ValidationError, json.JSONDecodeError):
            return IntentDecision(
                intent='knowledge_qa',
                chapter_no=chapter_no,
                resource_type=resource_type,
                student_level=level,
                reason='分类器异常，安全回退到知识问答',
            )


def build_course_agent_graph():  # noqa: C901 - graph wiring keeps node closures together
    def normalize_input(state: CourseAgentState) -> CourseAgentState:
        messages = state.get('messages') or []
        last_user_index = next(
            (index for index in range(len(messages) - 1, -1, -1) if messages[index].get('role') == 'user'),
            -1,
        )
        query = _message_text(messages[last_user_index].get('content')) if last_user_index >= 0 else ''
        history_messages = [
            message
            for message in messages[:last_user_index]
            if message.get('role') in {'user', 'assistant'} and _message_text(message.get('content')).strip()
        ][-6:]
        history_context = '\n'.join(
            f"{'学生' if message.get('role') == 'user' else '助教'}：{_message_text(message.get('content')).strip()}"
            for message in history_messages
        )[-4000:]
        system_prompt = _immutable_system_prompt(messages)
        chapter_no, chapter_invalid = _detect_chapter(query)
        chapter_explicit = chapter_no is not None
        if chapter_no is None and not chapter_invalid:
            chapter_no = _infer_concept_chapter(query)
        errors: list[str] = []
        if not query.strip():
            errors.append('请输入需要学习或查询的问题。')
        elif len(query) > 12000:
            errors.append('输入内容过长，请缩短后重试。')
        if chapter_invalid:
            errors.append('课程章节编号必须是1到15。')
        return {
            'original_query': query.strip(),
            'query': query.strip(),
            'history_context': history_context,
            'system_prompt': system_prompt,
            'chapter_no': chapter_no,
            'chapter_explicit': chapter_explicit,
            'resource_type': _detect_resource_type(query),
            'student_level': _detect_level(query),
            'has_student_attempt': False,
            'academic_integrity_block': _is_whole_assignment_request(query),
            'errors': errors,
            'retry_count': 0,
            'grounding_retry_count': 0,
        }

    async def rewrite_query(
        state: CourseAgentState,
        runtime: Runtime[CourseAgentRuntime],
    ) -> CourseAgentState:
        runtime = runtime.context
        if state.get('errors') or not _needs_context_rewrite(
            state.get('query', ''), state.get('history_context', '')
        ):
            return {}
        await runtime.emit_status('正在结合对话上下文理解追问…')
        original = state['query']
        history = state['history_context']
        prompt = f"""将学生的当前追问改写成可独立检索的完整问题。
要求：解析“它、这个、前者、后者”等指代；保留章节、代码和限制条件；不得回答问题；只输出改写后的问题。

最近对话：
{history}

当前追问：
{original}"""
        try:
            rewritten = (await runtime.call_model(
                [
                    {'role': 'system', 'content': '你是课程检索查询改写器，只输出一个完整问题。'},
                    {'role': 'user', 'content': prompt},
                ],
                temperature=0.0,
            )).strip().strip('`').strip('“”"')
            if not rewritten or len(rewritten) > 2000 or '\n\n' in rewritten:
                raise ValueError('查询改写结果无效')
        except Exception:
            prior_user = next(
                (
                    line.removeprefix('学生：')
                    for line in reversed(history.splitlines())
                    if line.startswith('学生：')
                ),
                history,
            )
            rewritten = f'{prior_user}；追问：{original}'
        chapter_no, chapter_invalid = _detect_chapter(rewritten)
        chapter_explicit = chapter_no is not None
        if chapter_no is None and not chapter_invalid:
            chapter_no = _infer_concept_chapter(rewritten)
        updates: CourseAgentState = {
            'query': rewritten,
            'chapter_no': chapter_no,
            'chapter_explicit': chapter_explicit,
            'resource_type': _detect_resource_type(rewritten),
            'student_level': _detect_level(rewritten),
        }
        if chapter_invalid:
            updates['errors'] = [*state.get('errors', []), '课程章节编号必须是1到15。']
        return updates

    async def classify_intent(
        state: CourseAgentState,
        runtime: Runtime[CourseAgentRuntime],
    ) -> CourseAgentState:
        runtime = runtime.context
        if state.get('errors'):
            return {'intent': 'invalid_input'}
        if state.get('academic_integrity_block'):
            return {
                'intent': 'answer_review',
                'chapter_no': state.get('chapter_no'),
                'resource_type': state.get('resource_type', 'all'),
                'student_level': state.get('student_level', '初学者'),
                'has_student_attempt': False,
            }
        await runtime.emit_status('正在判断学习任务类型…')
        decision = await runtime.classify(state)
        return {
            'intent': decision.intent,
            'chapter_no': decision.chapter_no,
            'resource_type': normalize_resource_type(decision.resource_type),
            'student_level': decision.student_level,
            'has_student_attempt': decision.has_student_attempt,
        }

    def route_intent(state: CourseAgentState) -> str:
        if state.get('errors'):
            return 'invalid_input'
        if state.get('academic_integrity_block'):
            return 'academic_integrity'
        return state.get('intent', 'knowledge_qa')

    async def retrieve_knowledge(
        state: CourseAgentState,
        runtime: Runtime[CourseAgentRuntime],
    ) -> CourseAgentState:
        runtime = runtime.context
        await runtime.emit_status('正在进行向量与BM25混合召回并重排序…')
        try:
            chunks = await retrieve_core_chunks(
                runtime.request,
                runtime.user,
                runtime.course_data,
                state['query'],
                chapter_no=state.get('chapter_no'),
                resource_type=state.get('resource_type', 'all'),
                top_k=runtime.top_k,
                min_score=runtime.min_score,
                bm25_weight=runtime.bm25_weight,
                candidate_k=runtime.candidate_k,
                rerank_top_n=runtime.rerank_top_n,
                rerank_min_score=runtime.rerank_min_score,
            )
            return {
                'retrieved_chunks': chunks,
                'errors': [],
            }
        except Exception as exc:
            return {
                'retrieved_chunks': [],
                'errors': [*state.get('errors', []), str(exc)],
                'error_kind': 'retrieval',
            }

    async def assess_evidence(
        state: CourseAgentState,
        runtime: Runtime[CourseAgentRuntime],
    ) -> CourseAgentState:
        runtime = runtime.context
        if state.get('error_kind') == 'retrieval' or state.get('errors'):
            return {'evidence_status': 'error'}
        chunks = state.get('retrieved_chunks') or []
        score, coverage, reranked = _evidence_metrics(state.get('query', ''), chunks)
        score_ok = not reranked or score >= runtime.evidence_min_score
        coverage_ok = coverage >= runtime.evidence_min_coverage
        if chunks and score_ok and coverage_ok:
            status = 'sufficient'
        elif state.get('retry_count', 0) < 1:
            status = 'retry'
        else:
            status = 'insufficient'
        log.info(
            'Course evidence status=%s score=%.4f coverage=%.4f chunks=%d method=%s retry=%d',
            status,
            score,
            coverage,
            len(chunks),
            chunks[0].get('ranking_method', 'unknown') if chunks else 'none',
            state.get('retry_count', 0),
        )
        await runtime.emit_status(
            '检索证据充分，正在准备回答…'
            if status == 'sufficient'
            else '当前证据不足，正在扩展查询并重试…'
            if status == 'retry'
            else '重新检索后证据仍不足…'
        )
        return {
            'evidence_status': status,
            'evidence_score': round(score, 4),
            'evidence_coverage': round(coverage, 4),
        }

    def evidence_route(state: CourseAgentState) -> str:
        return {
            'sufficient': 'compose',
            'retry': 'retry',
            'error': 'error',
        }.get(state.get('evidence_status'), 'uncertain')

    async def expand_query(
        state: CourseAgentState,
        runtime: Runtime[CourseAgentRuntime],
    ) -> CourseAgentState:
        runtime = runtime.context
        query = state.get('query', '')
        prompt = f"""把下面课程问题改写成一条更适合检索教材讲义的查询。
要求：保留原问题含义；补充必要的同义词、正式术语、定义/语法/步骤词；不要回答问题；只输出一行查询。

原查询：{query}"""
        try:
            expanded = (
                await runtime.call_model(
                    [
                        {'role': 'system', 'content': '你是Python课程检索查询扩展器。'},
                        {'role': 'user', 'content': prompt},
                    ],
                    temperature=0.0,
                )
            ).strip().strip('`').strip('“”"')
            if not expanded or len(expanded) > 2000 or '\n\n' in expanded:
                raise ValueError('查询扩展结果无效')
        except Exception:
            expanded = f'{query} 教材定义 基本概念 语法 原理 步骤 示例'
        return {
            'query': expanded,
            'chapter_no': state.get('chapter_no') if state.get('chapter_explicit') else None,
            'resource_type': 'all',
            'retrieved_chunks': [],
            'retry_count': state.get('retry_count', 0) + 1,
            'evidence_status': 'retry',
            'errors': [],
        }

    def chapter_tool(
        state: CourseAgentState,
        runtime: Runtime[CourseAgentRuntime],
    ) -> CourseAgentState:
        runtime = runtime.context
        try:
            if state.get('chapter_no') is None:
                result = runtime.course_data.course_outline()
            else:
                result = runtime.course_data.chapter_materials(state['chapter_no'], state.get('resource_type', 'all'))
            return {'tool_result': result}
        except Exception as exc:
            return {
                'errors': [*state.get('errors', []), str(exc)],
                'error_kind': 'tool',
            }

    def practice_tool(
        state: CourseAgentState,
        runtime: Runtime[CourseAgentRuntime],
    ) -> CourseAgentState:
        runtime = runtime.context
        chapter_no = state.get('chapter_no')
        if chapter_no is None:
            return {'errors': [*state.get('errors', []), '请先指定需要练习的章节（第1章至第15章）。']}
        count_match = re.search(r'(\d+)\s*(?:道|个)', state['query'])
        count = int(count_match.group(1)) if count_match else 3
        if not 1 <= count <= 5:
            return {'errors': [*state.get('errors', []), '每次抽题数量必须是1到5。']}
        try:
            return {'tool_result': runtime.course_data.sample_exercises(chapter_no, count=count)}
        except Exception as exc:
            return {
                'errors': [*state.get('errors', []), str(exc)],
                'error_kind': 'tool',
            }

    def tool_route(state: CourseAgentState) -> str:
        return 'error' if state.get('errors') else 'compose'

    def answer_attempt_route(state: CourseAgentState) -> str:
        return 'retrieve' if state.get('has_student_attempt') else 'ask_attempt'

    async def compose_answer(
        state: CourseAgentState,
        runtime: Runtime[CourseAgentRuntime],
    ) -> CourseAgentState:
        runtime = runtime.context
        await runtime.emit_status('正在组织课程助教回答…')
        chunks = state.get('retrieved_chunks') or []
        evidence = _format_evidence(chunks)
        tool_result = state.get('tool_result')
        intent_instructions = {
            'knowledge_qa': (
                '回答课程知识问题。先给结论，再综合多条相关资料解释；不要只依据第一条资料。'
                '若资料包含列表、表格或分散在相邻知识块中，应合并后完整回答。只使用所给资料。'
            ),
            'concept_explain': (
                '先用通俗语言解释，再给出教材中的正式定义和简短示例；'
                '综合多条相关资料，不要只复述第一条。只使用所给资料。'
            ),
            'chapter_query': '准确概括工具结果中的章节名称、资料和数量，不得自行补充统计。',
            'practice_generate': (
                '根据抽取材料生成练习，不照抄整套原题，不提供完整答案。'
                '每题标明章节、知识点、难度、题目和作答要求，可以给一条提示。'
            ),
            'answer_review': (
                '只评价学生已经提交的答案或代码。必须原样使用“正确之处”“存在问题”“改进建议”“自我检查”四个标题组织；'
                '先给提示和局部修正，不把整份作业重写成可直接提交的成品。'
            ),
        }
        system_prompt = state.get('system_prompt') or '你是Python程序设计基础课程AI助教。'
        student_level = state.get('student_level', '初学者')
        task_prompt = f"""{intent_instructions.get(state.get('intent'), intent_instructions['knowledge_qa'])}
学生水平：{student_level}
难度适配：{_level_guidance(student_level)}
引用规则：基于检索资料的陈述使用[资料N]；不得引用未提供的资料；资料不足时明确说无法确认。
证据使用：优先采用直接回答问题的资料；同一结论可引用多条资料。若资料之间只是上下文衔接，应综合而非割裂作答。
代码说明：涉及代码时说明适用版本、关键语句、输入输出和必要依赖；资料明确标注syntax_error时必须指出该代码不可直接运行。
学术诚信：不得代写整份作业、整套习题或可直接提交的实验报告。面对作业优先提供提示、思路、分步骤指导和自检方法。练习题不立即给出完整答案。
默认格式：使用“结论—解释或步骤—示例（需要时）—来源—自我检查或下一步（需要时）”；答案点评使用前述四段式结构。

用户原始问题：
{state.get('original_query') or state['query']}

用于检索的独立问题：
{state['query']}

检索资料：
{evidence or '无'}

结构化工具结果：
{json.dumps(tool_result, ensure_ascii=False) if tool_result else '无'}"""
        try:
            answer = await runtime.call_model(
                [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': task_prompt},
                ]
            )
            return {'draft_answer': answer}
        except Exception as exc:
            return {
                'errors': [*state.get('errors', []), str(exc)],
                'error_kind': 'generation',
            }

    def answer_route(state: CourseAgentState) -> str:
        return 'error' if state.get('error_kind') == 'generation' or state.get('errors') else 'grounding'

    def grounding_guard(state: CourseAgentState) -> CourseAgentState:
        if state.get('error_kind') == 'generation' or state.get('errors'):
            return {'grounding_status': 'failed'}
        chunks = state.get('retrieved_chunks') or []
        if not chunks:
            return {'grounding_status': 'valid'}
        answer = state.get('draft_answer', '')
        labels = _citation_labels(answer)
        valid = bool(labels) and all(1 <= label <= len(chunks) for label in labels)
        if valid:
            return {'grounding_status': 'valid'}
        if state.get('grounding_retry_count', 0) < 1:
            log.info('Course answer has no valid inline citations; requesting one revision')
            return {'grounding_status': 'revise'}
        return {
            'grounding_status': 'failed',
            'error_kind': 'grounding',
            'errors': [*state.get('errors', []), '回答未能通过资料引用校验'],
        }

    def grounding_route(state: CourseAgentState) -> str:
        return {
            'valid': 'valid',
            'revise': 'revise',
        }.get(state.get('grounding_status'), 'failed')

    async def revise_answer(
        state: CourseAgentState,
        runtime: Runtime[CourseAgentRuntime],
    ) -> CourseAgentState:
        runtime = runtime.context
        await runtime.emit_status('正在校验回答依据并修订引用…')
        evidence = _format_evidence(state.get('retrieved_chunks') or [])
        prompt = f"""修订下面的课程助教回答，使所有课程事实都有所给资料支持。
要求：保留正确内容；删除无资料支持的断言；至少使用一个有效的[资料N]行内引用；不得使用不存在的编号；不要解释修订过程。

用户问题：
{state.get('original_query') or state.get('query', '')}

检索资料：
{evidence}

待修订回答：
{state.get('draft_answer', '')}"""
        try:
            answer = await runtime.call_model(
                [
                    {'role': 'system', 'content': state.get('system_prompt') or load_course_system_prompt()},
                    {'role': 'user', 'content': prompt},
                ],
                temperature=0.0,
            )
            return {
                'draft_answer': answer,
                'grounding_retry_count': state.get('grounding_retry_count', 0) + 1,
                'grounding_status': 'revise',
            }
        except Exception as exc:
            return {
                'errors': [*state.get('errors', []), str(exc)],
                'error_kind': 'generation',
                'grounding_status': 'failed',
            }

    def citation_guard(state: CourseAgentState) -> CourseAgentState:
        answer = _guard_keyword_count(
            state.get('original_query') or state.get('query', ''),
            state.get('draft_answer', '').strip(),
        )
        chunks = state.get('retrieved_chunks') or []
        invalid_labels = [
            int(label) for label in re.findall(r'\[资料(\d+)\]', answer) if int(label) < 1 or int(label) > len(chunks)
        ]
        if invalid_labels:
            answer = re.sub(r'\[资料(?:' + '|'.join(map(str, invalid_labels)) + r')\]', '', answer)
        referenced = {
            int(label)
            for label in re.findall(r'\[资料(\d+)\]', answer)
            if 1 <= int(label) <= len(chunks)
        }
        selected_chunks = (
            [chunk for index, chunk in enumerate(chunks, start=1) if index in referenced]
            if referenced
            else []
        )
        sources: list[str] = []
        for chunk in selected_chunks:
            label = _source_label(chunk)
            if label not in sources:
                sources.append(label)
        tool_result = state.get('tool_result') or {}
        for material in tool_result.get('materials', []):
            source = material.get('source_path')
            if source and source not in sources:
                sources.append(source)
        for exercise in tool_result.get('exercises', []):
            source = exercise.get('source')
            if source and source not in sources:
                sources.append(source)
        has_source_section = bool(
            re.search(
                r'(?im)^\s*(?:#{1,6}\s*)?(?:\*\*)?(?:资料)?来源(?:\*\*)?\s*[:：]?\s*$',
                answer,
            )
        )
        if sources and not has_source_section:
            answer += '\n\n资料来源：\n' + '\n'.join(f'- {source}' for source in sources)
        return {'final_answer': answer or '根据现有资料无法生成可靠回答。'}

    def invalid_response(state: CourseAgentState) -> CourseAgentState:
        return {'final_answer': '\n'.join(state.get('errors') or ['输入无效，请重新描述问题。'])}

    def out_of_scope_response(state: CourseAgentState) -> CourseAgentState:
        return {
            'final_answer': (
                '这超出了《Python程序设计基础》课程范围。请改为询问课程第1至15章的知识、代码、练习或学习方法。'
            )
        }

    def uncertain_response(state: CourseAgentState) -> CourseAgentState:
        chapter = state.get('chapter_no')
        suggestion = f'建议查阅第{chapter}章相关讲义。' if chapter else '建议补充具体章节或知识点。'
        return {'final_answer': f'根据现有课程资料无法确认。{suggestion}'}

    def ask_attempt_response(state: CourseAgentState) -> CourseAgentState:
        return {'final_answer': '请先提供你的答案、代码或解题过程。我会先指出正确之处，再分析问题并给出分步改进建议。'}

    def academic_integrity_response(state: CourseAgentState) -> CourseAgentState:
        return {
            'final_answer': (
                '我不能代替你完成整份作业、整套习题或可直接提交的报告。'
                '你可以选择其中一道题，并提供已经尝试的答案、代码或卡住的步骤；'
                '我会依据课程资料给出提示、解题思路、分步骤指导和自我检查方法。'
            )
        }

    def error_response(state: CourseAgentState) -> CourseAgentState:
        kind = state.get('error_kind') or 'unknown'
        detail = (state.get('errors') or ['未知错误'])[-1]
        log.error('Course agent %s error: %s', kind, detail)
        messages = {
            'retrieval': '课程知识库检索暂时不可用，请稍后重试。',
            'generation': '基础模型暂时无法生成回答，请稍后重试。',
            'tool': '课程资料工具暂时不可用，请稍后重试。',
            'grounding': '已找到相关资料，但回答未能通过引用校验，请重试。',
        }
        return {'final_answer': messages.get(kind, '课程智能体暂时无法完成该操作，请稍后重试。')}

    async def finish(
        state: CourseAgentState,
        runtime: Runtime[CourseAgentRuntime],
    ) -> CourseAgentState:
        runtime = runtime.context
        await runtime.emit_status('课程助教回答完成', done=True)
        return {}

    graph = StateGraph(CourseAgentState, context_schema=CourseAgentRuntime)
    graph.add_node('normalize_input', normalize_input)
    graph.add_node('rewrite_query', rewrite_query)
    graph.add_node('classify_intent', classify_intent)
    graph.add_node('retrieve_knowledge', retrieve_knowledge)
    graph.add_node('assess_evidence', assess_evidence)
    graph.add_node('expand_query', expand_query)
    graph.add_node('chapter_tool', chapter_tool)
    graph.add_node('practice_tool', practice_tool)
    graph.add_node('compose_answer', compose_answer)
    graph.add_node('grounding_guard', grounding_guard)
    graph.add_node('revise_answer', revise_answer)
    graph.add_node('citation_guard', citation_guard)
    graph.add_node('invalid_response', invalid_response)
    graph.add_node('out_of_scope_response', out_of_scope_response)
    graph.add_node('uncertain_response', uncertain_response)
    graph.add_node('ask_attempt_response', ask_attempt_response)
    graph.add_node('academic_integrity_response', academic_integrity_response)
    graph.add_node('error_response', error_response)
    graph.add_node('finish', finish)

    graph.add_edge(START, 'normalize_input')
    graph.add_edge('normalize_input', 'rewrite_query')
    graph.add_edge('rewrite_query', 'classify_intent')
    graph.add_conditional_edges(
        'classify_intent',
        route_intent,
        {
            'invalid_input': 'invalid_response',
            'out_of_scope': 'out_of_scope_response',
            'academic_integrity': 'academic_integrity_response',
            'chapter_query': 'chapter_tool',
            'practice_generate': 'practice_tool',
            'answer_review': 'answer_attempt_gate',
            'knowledge_qa': 'retrieve_knowledge',
            'concept_explain': 'retrieve_knowledge',
        },
    )
    graph.add_node('answer_attempt_gate', lambda state: {})
    graph.add_conditional_edges(
        'answer_attempt_gate',
        answer_attempt_route,
        {'retrieve': 'retrieve_knowledge', 'ask_attempt': 'ask_attempt_response'},
    )
    graph.add_edge('retrieve_knowledge', 'assess_evidence')
    graph.add_conditional_edges(
        'assess_evidence',
        evidence_route,
        {
            'compose': 'compose_answer',
            'retry': 'expand_query',
            'uncertain': 'uncertain_response',
            'error': 'error_response',
        },
    )
    graph.add_edge('expand_query', 'retrieve_knowledge')
    graph.add_conditional_edges(
        'chapter_tool',
        tool_route,
        {'compose': 'compose_answer', 'error': 'error_response'},
    )
    graph.add_conditional_edges(
        'practice_tool',
        tool_route,
        {'compose': 'compose_answer', 'error': 'error_response'},
    )
    graph.add_conditional_edges(
        'compose_answer',
        answer_route,
        {'grounding': 'grounding_guard', 'error': 'error_response'},
    )
    graph.add_conditional_edges(
        'grounding_guard',
        grounding_route,
        {'valid': 'citation_guard', 'revise': 'revise_answer', 'failed': 'error_response'},
    )
    graph.add_edge('revise_answer', 'grounding_guard')
    for node in (
        'citation_guard',
        'invalid_response',
        'out_of_scope_response',
        'uncertain_response',
        'ask_attempt_response',
        'academic_integrity_response',
        'error_response',
    ):
        graph.add_edge(node, 'finish')
    graph.add_edge('finish', END)
    return graph.compile()
