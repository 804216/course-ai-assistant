from __future__ import annotations

from typing import Any, Literal, TypedDict

CourseIntent = Literal[
    'knowledge_qa',
    'concept_explain',
    'chapter_query',
    'practice_generate',
    'answer_review',
    'out_of_scope',
    'invalid_input',
]


class RetrievedChunk(TypedDict, total=False):
    content: str
    source: str
    chapter_no: int
    chapter_title: str
    resource_type: str
    page_start: int
    page_end: int
    line_start: int
    line_end: int
    ordinal: int
    section_title: str
    score: float
    fusion_score: float
    rerank_score: float | None
    ranking_method: str
    group_size: int


class CourseAgentState(TypedDict, total=False):
    messages: list[dict[str, Any]]
    original_query: str
    query: str
    history_context: str
    system_prompt: str
    intent: CourseIntent
    chapter_no: int | None
    chapter_explicit: bool
    resource_type: str
    student_level: str
    has_student_attempt: bool
    academic_integrity_block: bool
    retrieved_chunks: list[RetrievedChunk]
    evidence_status: Literal['sufficient', 'retry', 'insufficient', 'error']
    evidence_score: float
    evidence_coverage: float
    tool_result: dict[str, Any]
    draft_answer: str
    grounding_status: Literal['valid', 'revise', 'failed']
    final_answer: str
    errors: list[str]
    error_kind: Literal['retrieval', 'generation', 'tool', 'grounding']
    retry_count: int
    grounding_retry_count: int
