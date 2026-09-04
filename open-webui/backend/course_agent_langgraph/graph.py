from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field, ValidationError

from .course_data import CHAPTER_TITLES, CourseData, normalize_resource_type
from .model_gateway import invoke_base_model
from .retrieval import retrieve_core_chunks
from .state import CourseAgentState, CourseIntent


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
    if any(word in query for word in ('零基础', '小白', '没学过')):
        return '零基础'
    if any(word in query for word in ('考试', '备考', '复习', '提高')):
        return '备考复习'
    return '初学者'


def _deterministic_intent(query: str) -> CourseIntent | None:
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


@dataclass
class CourseAgentRuntime:
    request: Any
    user: Any
    data_dir: Path
    base_model_id: str = 'deepseek-v4-flash'
    top_k: int = 5
    min_score: float = 0.0
    bm25_weight: float = 0.3
    event_emitter: Any = None

    def __post_init__(self) -> None:
        self.course_data = CourseData(self.data_dir)

    async def emit_status(self, description: str, done: bool = False) -> None:
        if self.event_emitter:
            await self.event_emitter(
                {
                    'type': 'status',
                    'data': {'description': description, 'done': done},
                }
            )

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


def build_course_agent_graph(runtime: CourseAgentRuntime):  # noqa: C901 - graph wiring keeps node closures together
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
        system_prompt = '\n\n'.join(
            _message_text(message.get('content')) for message in messages if message.get('role') == 'system'
        ).strip()
        chapter_no, chapter_invalid = _detect_chapter(query)
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
            'resource_type': _detect_resource_type(query),
            'student_level': _detect_level(query),
            'has_student_attempt': False,
            'errors': errors,
            'retry_count': 0,
        }

    async def rewrite_query(state: CourseAgentState) -> CourseAgentState:
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
        if chapter_no is None and not chapter_invalid:
            chapter_no = _infer_concept_chapter(rewritten)
        updates: CourseAgentState = {
            'query': rewritten,
            'chapter_no': chapter_no,
            'resource_type': _detect_resource_type(rewritten),
            'student_level': _detect_level(rewritten),
        }
        if chapter_invalid:
            updates['errors'] = [*state.get('errors', []), '课程章节编号必须是1到15。']
        return updates

    async def classify_intent(state: CourseAgentState) -> CourseAgentState:
        if state.get('errors'):
            return {'intent': 'invalid_input'}
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
        return state.get('intent', 'knowledge_qa')

    async def retrieve_knowledge(state: CourseAgentState) -> CourseAgentState:
        await runtime.emit_status('正在检索课程核心知识库…')
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
            )
            return {'retrieved_chunks': chunks}
        except Exception as exc:
            return {'retrieved_chunks': [], 'errors': [*state.get('errors', []), str(exc)]}

    def evidence_route(state: CourseAgentState) -> str:
        return 'compose' if state.get('retrieved_chunks') else 'uncertain'

    def chapter_tool(state: CourseAgentState) -> CourseAgentState:
        try:
            if state.get('chapter_no') is None:
                result = runtime.course_data.course_outline()
            else:
                result = runtime.course_data.chapter_materials(state['chapter_no'], state.get('resource_type', 'all'))
            return {'tool_result': result}
        except Exception as exc:
            return {'errors': [*state.get('errors', []), str(exc)]}

    def practice_tool(state: CourseAgentState) -> CourseAgentState:
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
            return {'errors': [*state.get('errors', []), str(exc)]}

    def tool_route(state: CourseAgentState) -> str:
        return 'error' if state.get('errors') else 'compose'

    def answer_attempt_route(state: CourseAgentState) -> str:
        return 'retrieve' if state.get('has_student_attempt') else 'ask_attempt'

    async def compose_answer(state: CourseAgentState) -> CourseAgentState:
        await runtime.emit_status('正在组织课程助教回答…')
        chunks = state.get('retrieved_chunks') or []
        evidence = '\n\n'.join(
            f'[资料{index}] 来源={chunk["source"]}；章节={chunk.get("chapter_no")}；'
            f'页码={chunk.get("page_start") or "未知"}\n{chunk["content"]}'
            for index, chunk in enumerate(chunks, start=1)
        )
        tool_result = state.get('tool_result')
        intent_instructions = {
            'knowledge_qa': '回答课程知识问题。先给结论，再解释；只使用所给资料。',
            'concept_explain': '面向指定学习水平通俗解释，并给出简短示例。只使用所给资料。',
            'chapter_query': '准确概括工具结果中的章节名称、资料和数量，不得自行补充统计。',
            'practice_generate': '根据抽取材料给出练习题，不提供完整答案；标明章节和难度。',
            'answer_review': '先指出学生答案正确之处，再指出问题，最后给出分步改进和自检方法。',
        }
        system_prompt = state.get('system_prompt') or '你是Python程序设计基础课程AI助教。'
        task_prompt = f"""{intent_instructions.get(state.get('intent'), intent_instructions['knowledge_qa'])}
学生水平：{state.get('student_level', '初学者')}
引用规则：基于检索资料的陈述使用[资料N]；不得引用未提供的资料；资料不足时明确说无法确认。
学术诚信：不得代写整份作业。练习题不立即给出完整答案。

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
            return {'errors': [*state.get('errors', []), str(exc)]}

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
            else chunks[:1]
        )
        sources: list[str] = []
        for chunk in selected_chunks:
            source = chunk['source']
            page = chunk.get('page_start')
            label = f'{source}' + (f'，第{page}页' if page else '')
            if label not in sources:
                sources.append(label)
        tool_result = state.get('tool_result') or {}
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

    def error_response(state: CourseAgentState) -> CourseAgentState:
        detail = state.get('errors', ['未知错误'])[-1]
        return {'final_answer': f'课程智能体暂时无法完成该操作：{detail}'}

    async def finish(state: CourseAgentState) -> CourseAgentState:
        await runtime.emit_status('课程助教回答完成', done=True)
        return {}

    graph = StateGraph(CourseAgentState)
    graph.add_node('normalize_input', normalize_input)
    graph.add_node('rewrite_query', rewrite_query)
    graph.add_node('classify_intent', classify_intent)
    graph.add_node('retrieve_knowledge', retrieve_knowledge)
    graph.add_node('chapter_tool', chapter_tool)
    graph.add_node('practice_tool', practice_tool)
    graph.add_node('compose_answer', compose_answer)
    graph.add_node('citation_guard', citation_guard)
    graph.add_node('invalid_response', invalid_response)
    graph.add_node('out_of_scope_response', out_of_scope_response)
    graph.add_node('uncertain_response', uncertain_response)
    graph.add_node('ask_attempt_response', ask_attempt_response)
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
    graph.add_conditional_edges(
        'retrieve_knowledge',
        evidence_route,
        {'compose': 'compose_answer', 'uncertain': 'uncertain_response'},
    )
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
    graph.add_edge('compose_answer', 'citation_guard')
    for node in (
        'citation_guard',
        'invalid_response',
        'out_of_scope_response',
        'uncertain_response',
        'ask_attempt_response',
        'error_response',
    ):
        graph.add_edge(node, 'finish')
    graph.add_edge('finish', END)
    return graph.compile()
