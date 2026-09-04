from __future__ import annotations

from functools import lru_cache
from pathlib import Path

FALLBACK_SYSTEM_PROMPT = """你是“Python程序设计基础 AI 助教”，服务于《Python程序设计基础教程（微课版）》。
只回答本课程第1至15章相关问题。回答应先给结论再解释，并给出真实资料来源。
资料不足时明确回答“根据现有课程资料无法确认”，不得编造。
不得代替学生完成整份作业，应优先提供提示、思路和分步骤指导。"""


@lru_cache(maxsize=1)
def load_course_system_prompt() -> str:
    project_root = Path(__file__).resolve().parents[3]
    prompt_path = project_root / 'tools' / 'course_kb' / 'assistant_prompt.txt'
    if prompt_path.is_file():
        prompt = prompt_path.read_text(encoding='utf-8').strip()
        if prompt:
            return prompt
    return FALLBACK_SYSTEM_PROMPT
