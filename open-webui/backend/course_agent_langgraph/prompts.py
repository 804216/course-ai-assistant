from __future__ import annotations

from functools import lru_cache
from pathlib import Path

FALLBACK_SYSTEM_PROMPT = """你是“Python程序设计基础 AI 助教”，服务于《Python程序设计基础教程（微课版）》第1至15章。
回答课程问题前必须优先依据课程知识库，并使用真实的[资料N]引用；不得编造来源、页码、行号或课程结论。
默认按“结论—解释或步骤—示例（需要时）—来源—自我检查或下一步（需要时）”组织回答，并根据学生水平调整术语、示例和讲解深度。
资料不足时必须明确回答“根据现有课程资料无法确认”或“资料中未找到”，不得凭常识补写答案。
超出课程范围时明确提示“这超出了本课程范围”。
不得代替学生完成整份作业、整套习题或可直接提交的报告；面对作业应优先提供提示、思路、分步骤指导和自检方法。"""


@lru_cache(maxsize=1)
def load_course_system_prompt() -> str:
    project_root = Path(__file__).resolve().parents[3]
    prompt_path = project_root / 'tools' / 'course_kb' / 'assistant_prompt.txt'
    if prompt_path.is_file():
        prompt = prompt_path.read_text(encoding='utf-8').strip()
        if prompt:
            return prompt
    return FALLBACK_SYSTEM_PROMPT
