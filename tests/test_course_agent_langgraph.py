from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "open-webui" / "backend"))

from course_agent_langgraph.graph import (  # noqa: E402
    CourseAgentRuntime,
    IntentDecision,
    _deterministic_intent,
    _infer_concept_chapter,
    _guard_keyword_count,
    _needs_context_rewrite,
    build_course_agent_graph,
)
from course_agent_langgraph.retrieval import (  # noqa: E402
    _bm25_rank,
    _bm25_query_text,
    _bm25_tokenize,
    _expand_neighbor_context,
    _is_exhaustive_request,
    _lexical_query_terms,
    _lexical_relevance,
    _promote_precise_bm25_anchor,
    _promote_definition_anchor,
    _weighted_rrf,
)


class FakeCourseData:
    def course_outline(self) -> dict[str, Any]:
        return {
            "build_id": "test-v1",
            "chapters": [{"chapter_no": 6, "chapter_title": "函数"}],
        }

    def chapter_materials(self, chapter_no: int, resource_type: str) -> dict[str, Any]:
        return {
            "build_id": "test-v1",
            "chapter_no": chapter_no,
            "chapter_title": "函数",
            "resource_type": resource_type,
            "chunk_counts": {"code": 17},
            "materials": [],
        }

    def sample_exercises(self, chapter_no: int, count: int = 3) -> dict[str, Any]:
        return {
            "chapter_no": chapter_no,
            "chapter_title": "函数",
            "count": count,
            "exercises": [{"source": "第06章-函数-习题.pdf", "content": "练习题"}],
        }


class FakeRuntime:
    def __init__(self, decision: IntentDecision | None = None, model_answer: str = "测试回答") -> None:
        self.course_data = FakeCourseData()
        self.decision = decision
        self.model_answer = model_answer
        self.request = object()
        self.user = object()
        self.top_k = 5
        self.min_score = 0.0
        self.bm25_weight = 0.3
        self.statuses: list[tuple[str, bool]] = []

    async def emit_status(self, description: str, done: bool = False) -> None:
        self.statuses.append((description, done))

    async def classify(self, state):
        if self.decision:
            return self.decision
        return IntentDecision(
            intent="chapter_query",
            chapter_no=state.get("chapter_no"),
            resource_type=state.get("resource_type", "all"),
        )

    async def call_model(self, messages, temperature: float = 0.2) -> str:
        prompt = messages[-1]["content"]
        if "当前追问" in prompt and "改写" in prompt:
            return "为什么Python元组不能修改？"
        if '"code": 17' in prompt:
            return "第6章是函数，共有17个示例代码知识块。"
        if '"exercises":' in prompt:
            return "第6章自测题：请编写一个带默认参数的函数。"
        return self.model_answer


def test_exhaustive_keyword_query_gets_exact_lexical_anchors() -> None:
    query = "python中所有的关键字"
    assert _is_exhaustive_request(query) is True
    assert _lexical_query_terms(query)[:2] == ["所有关键字", "关键字"]
    assert "保留字" in _lexical_query_terms(query)


def test_ordinary_semantic_query_keeps_vector_only_path() -> None:
    assert _lexical_query_terms("解释一下Python关键字") == []


def test_complete_keyword_table_outranks_dictionary_key_content() -> None:
    terms = _lexical_query_terms("python中所有的关键字")
    keyword_table = "表2-1 Python语言中的所有关键字 and as assert async await"
    dictionary_keys = "可以使用字典对象的keys()方法获取键列表"
    assert _lexical_relevance(keyword_table, terms, True) > _lexical_relevance(
        dictionary_keys, terms, True
    )


def test_bm25_tokenizer_supports_chinese_and_python_identifiers() -> None:
    tokens = _bm25_tokenize("函数参数使用 keyword.kwlist 查看")
    assert "函数" in tokens
    assert "参数" in tokens
    assert "keyword" in tokens
    assert "kwlist" in tokens


def test_bm25_tokenizer_normalizes_pep8_spelling() -> None:
    assert "pep8" in _bm25_tokenize("PEP 8 编码规范")


def test_definition_query_expands_to_textbook_definition_terms() -> None:
    expanded = _bm25_query_text("在Python中，什么是函数")
    assert "函数" in expanded
    assert "基本定义" in expanded


def test_function_definition_query_infers_chapter_six_without_overfiltering() -> None:
    assert _infer_concept_chapter("在Python中，什么是函数？") == 6
    assert _infer_concept_chapter("input函数如何使用？") is None


@pytest.mark.asyncio
async def test_classifier_cannot_invent_a_chapter_filter(monkeypatch) -> None:
    runtime = CourseAgentRuntime(request=object(), user=object(), data_dir=PROJECT_ROOT)

    async def fake_call_model(messages, temperature=0.2):
        return '{"intent":"knowledge_qa","chapter_no":0,"resource_type":"all"}'

    monkeypatch.setattr(runtime, "call_model", fake_call_model)
    decision = await runtime.classify(
        {
            "query": "pickle.dumps和pickle.loads如何配合？",
            "chapter_no": None,
            "resource_type": "all",
            "student_level": "初学者",
        }
    )
    assert decision.chapter_no is None


def test_bm25_ranks_keyword_table_above_dictionary_keys() -> None:
    ids = ["dictionary", "keywords", "loop"]
    documents = [
        "字典对象可以使用keys方法获取所有键",
        "表2-1 Python语言中的所有关键字：and as assert async await break",
        "while循环和for循环用于重复执行代码",
    ]
    ranked = _bm25_rank("python中所有的关键字", ids, documents, limit=3)
    assert ranked[0] == "keywords"


def test_weighted_rrf_rewards_candidates_found_by_both_retrievers() -> None:
    fused = _weighted_rrf(
        vector_ids=["vector-only", "shared", "third"],
        bm25_ids=["shared", "bm25-only", "third"],
        bm25_weight=0.5,
        limit=4,
    )
    assert fused[0][0] == "shared"
    assert 0.0 < fused[0][1] <= 1.0


def test_neighbor_expansion_keeps_adjacent_chunks_from_same_file() -> None:
    rows = {
        f"p{ordinal}": ("content", {"file_id": "lecture", "ordinal": ordinal})
        for ordinal in range(8, 13)
    }
    rows["other"] = ("content", {"file_id": "other", "ordinal": 9})
    expanded = _expand_neighbor_context(
        [("p10", 1.0), ("other", 0.9)], rows, "pickle dumps 和 loads 的完整过程", 5
    )
    assert [item_id for item_id, _ in expanded] == ["p10", "p9", "p11", "p8", "p12"]


def test_short_follow_up_promotes_bm25_anchor() -> None:
    promoted = _promote_precise_bm25_anchor(
        "为什么元组不能修改？",
        [("vector", 0.9), ("lexical", 0.7)],
        ["lexical", "other"],
    )
    assert promoted[0][0] == "lexical"


def test_dotted_python_api_promotes_bm25_anchor() -> None:
    promoted = _promote_precise_bm25_anchor(
        "请说明pickle.dumps和pickle.loads如何配合完成序列化与反序列化",
        [("vector", 0.9)],
        ["loads-page"],
    )
    assert promoted[0][0] == "loads-page"


def test_definition_anchor_prefers_syntax_page_over_later_example() -> None:
    rows = {
        "example": ("6.1.1 基本定义及调用\n\n下面给出一个函数实例。", {"section_title": "6.1.1 基本定义及调用"}),
        "definition": ("6.1 普通函数\n\n6.1.1 基本定义及调用\n定义函数的语法\ndef 函数名():", {"section_title": "6.1 普通函数"}),
    }
    promoted = _promote_definition_anchor(
        "什么是函数", [("example", 0.9), ("definition", 0.8)], ["example", "definition"], rows
    )
    assert promoted[0][0] == "definition"


def test_follow_up_detection_requires_history() -> None:
    assert _needs_context_rewrite("那后者为什么不能修改？", "学生：列表和元组有什么区别？")
    assert not _needs_context_rewrite("那后者为什么不能修改？", "")


def test_knowledge_question_is_not_misrouted_as_material_listing() -> None:
    query = "第6章中函数的参数传递方式有哪些？请依据课程资料回答并给出来源。"
    assert _deterministic_intent(query) == "knowledge_qa"
    assert _deterministic_intent("第6章有哪些资料和代码？") == "chapter_query"


def test_keyword_list_question_bypasses_probabilistic_classifier() -> None:
    assert _deterministic_intent("python中所有的关键字") == "knowledge_qa"


def test_complete_keyword_answer_count_is_guarded() -> None:
    keywords = " ".join(
        (
            "and", "as", "assert", "async", "await", "break", "class", "continue", "def",
            "del", "elif", "else", "except", "finally", "for", "from", "False", "global",
            "if", "import", "in", "is", "lambda", "nonlocal", "not", "None", "or", "pass",
            "raise", "return", "try", "True", "while", "with", "yield",
        )
    )
    guarded = _guard_keyword_count("Python中所有的关键字", f"共有33个关键字：{keywords}")
    assert "35 个关键字" in guarded
    assert "33个关键字" not in guarded


@pytest.mark.asyncio
async def test_chapter_query_routes_to_catalog_tool() -> None:
    runtime = FakeRuntime()
    graph = build_course_agent_graph(runtime)
    result = await graph.ainvoke(
        {
            "messages": [
                {"role": "user", "content": "第6章叫什么？示例代码有多少个知识块？"}
            ]
        }
    )
    assert result["intent"] == "chapter_query"
    assert result["tool_result"]["chunk_counts"] == {"code": 17}
    assert "函数" in result["final_answer"]
    assert "17" in result["final_answer"]
    assert runtime.statuses[-1][1] is True


@pytest.mark.asyncio
async def test_answer_review_requires_student_attempt() -> None:
    runtime = FakeRuntime(
        IntentDecision(
            intent="answer_review",
            chapter_no=6,
            resource_type="all",
            has_student_attempt=False,
        )
    )
    graph = build_course_agent_graph(runtime)
    result = await graph.ainvoke(
        {"messages": [{"role": "user", "content": "请帮我批改第6章作业"}]}
    )
    assert "请先提供你的答案" in result["final_answer"]


@pytest.mark.asyncio
async def test_out_of_scope_is_stopped_before_retrieval() -> None:
    runtime = FakeRuntime(IntentDecision(intent="out_of_scope"))
    graph = build_course_agent_graph(runtime)
    result = await graph.ainvoke(
        {"messages": [{"role": "user", "content": "今天有什么体育新闻？"}]}
    )
    assert result["intent"] == "out_of_scope"
    assert "超出了" in result["final_answer"]


@pytest.mark.asyncio
async def test_invalid_chapter_is_rejected_without_model_call() -> None:
    runtime = FakeRuntime()
    graph = build_course_agent_graph(runtime)
    result = await graph.ainvoke(
        {"messages": [{"role": "user", "content": "给我第16章的练习题"}]}
    )
    assert result["intent"] == "invalid_input"
    assert "1到15" in result["final_answer"]


@pytest.mark.asyncio
async def test_practice_tool_never_returns_answer_collection() -> None:
    runtime = FakeRuntime(
        IntentDecision(
            intent="practice_generate", chapter_no=6, resource_type="exercise_question"
        )
    )
    graph = build_course_agent_graph(runtime)
    result = await graph.ainvoke(
        {"messages": [{"role": "user", "content": "从第6章抽1道练习题"}]}
    )
    assert result["intent"] == "practice_generate"
    assert result["tool_result"]["count"] == 1
    assert "答案" not in str(result["tool_result"])


@pytest.mark.asyncio
async def test_follow_up_is_rewritten_before_retrieval(monkeypatch) -> None:
    captured: dict[str, str] = {}

    async def fake_retrieve(*args, **kwargs):
        captured["query"] = args[3]
        return [
            {
                "content": "元组创建后不能修改其中元素。",
                "source": "第04章-序列.pdf",
                "chapter_no": 4,
                "page_start": 20,
                "score": 1.0,
            }
        ]

    monkeypatch.setattr("course_agent_langgraph.graph.retrieve_core_chunks", fake_retrieve)
    runtime = FakeRuntime(IntentDecision(intent="knowledge_qa"))
    graph = build_course_agent_graph(runtime)
    result = await graph.ainvoke(
        {
            "messages": [
                {"role": "user", "content": "列表和元组最主要的区别？"},
                {"role": "assistant", "content": "列表可变，元组不可变。"},
                {"role": "user", "content": "那后者为什么不能修改？"},
            ]
        }
    )
    assert captured["query"] == "为什么Python元组不能修改？"
    assert result["original_query"] == "那后者为什么不能修改？"
    assert "第04章-序列.pdf" in result["final_answer"]


@pytest.mark.asyncio
async def test_citation_guard_lists_only_referenced_sources(monkeypatch) -> None:
    async def fake_retrieve(*args, **kwargs):
        return [
            {"content": "无关内容", "source": "无关.pdf", "page_start": 1, "score": 1.0},
            {"content": "函数参数内容", "source": "函数.pdf", "page_start": 8, "score": 0.9},
        ]

    monkeypatch.setattr("course_agent_langgraph.graph.retrieve_core_chunks", fake_retrieve)
    runtime = FakeRuntime(
        IntentDecision(intent="knowledge_qa"),
        model_answer="参数可以按位置或名称传入。[资料2]",
    )
    result = await build_course_agent_graph(runtime).ainvoke(
        {"messages": [{"role": "user", "content": "函数参数如何传递？"}]}
    )
    assert "函数.pdf，第8页" in result["final_answer"]
    assert "无关.pdf" not in result["final_answer"]
