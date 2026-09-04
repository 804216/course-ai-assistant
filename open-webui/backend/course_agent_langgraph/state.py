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
    ordinal: int
    section_title: str
    score: float


class CourseAgentState(TypedDict, total=False):
    messages: list[dict[str, Any]]
    original_query: str
    query: str
    history_context: str
    system_prompt: str
    intent: CourseIntent
    chapter_no: int | None
    resource_type: str
    student_level: str
    has_student_attempt: bool
    retrieved_chunks: list[RetrievedChunk]
    tool_result: dict[str, Any]
    draft_answer: str
    final_answer: str
    errors: list[str]
    retry_count: int
