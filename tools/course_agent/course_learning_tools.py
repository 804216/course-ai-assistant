"""
title: Python课程学习工具
author: course-ai-assistant
version: 1.1.0
description: 查询课程章节资料并从题目库抽取章节练习，供Python课程AI助教调用。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

try:
    from course_agent_langgraph.course_data import CourseData, normalize_resource_type
except ModuleNotFoundError:
    project_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(project_root / "open-webui" / "backend"))
    from course_agent_langgraph.course_data import CourseData, normalize_resource_type

_normalize_resource_type = normalize_resource_type


class Tools:
    def __init__(self) -> None:
        self.citation = True

    @staticmethod
    def _data() -> CourseData:
        return CourseData(Path(os.environ.get("DATA_DIR", "data")))

    def get_course_outline(self) -> str:
        """返回本课程的章节目录和每章可用资料数量。适用于询问课程范围、章节目录或有哪些学习资料。

        Returns:
            JSON格式的课程章节目录、核心知识块数和答案块数。
        """
        return json.dumps(self._data().course_outline(), ensure_ascii=False)

    def get_chapter_materials(self, chapter_no: int, resource_type: str = "all") -> str:
        """查询指定章节有哪些课程资料和知识块。只返回资料目录，不返回教材答案正文。

        :param chapter_no: 章节编号，课程说明用0，第1章到第15章用1到15。
        :param resource_type: 资料类型，可用all、lecture、exercise_question、code、syllabus，也可用中文讲义、题目、代码、大纲。
        :return: JSON格式的章节名称、资料文件、处理状态和知识块数量。
        """
        return json.dumps(
            self._data().chapter_materials(chapter_no, resource_type),
            ensure_ascii=False,
        )

    def sample_chapter_exercises(
        self, chapter_no: int, count: int = 3, seed: int = 0
    ) -> str:
        """从指定章节的习题题目集合中抽取练习材料，不读取参考答案。用于随机抽题或生成同类自测题。

        :param chapter_no: 章节编号，只允许1到15。
        :param count: 抽取数量，允许1到5，默认3。
        :param seed: 可选随机种子；为0时每天稳定变化，指定非零值可复现抽取结果。
        :return: JSON格式的题目材料、来源文件和页码。工具结果不包含参考答案。
        """
        return json.dumps(
            self._data().sample_exercises(chapter_no, count=count, seed=seed),
            ensure_ascii=False,
        )
