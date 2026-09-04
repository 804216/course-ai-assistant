"""
title: Python程序设计基础 AI 助教（LangGraph）
author: course-ai-assistant
version: 1.2.1
description: 使用LangGraph编排课程知识检索、章节查询、练习生成和学生答案分析。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from course_agent_langgraph.graph import CourseAgentRuntime, build_course_agent_graph
from course_agent_langgraph.model_gateway import invoke_base_model
from course_agent_langgraph.prompts import load_course_system_prompt
from open_webui.env import DATA_DIR
from open_webui.models.users import UserModel


class Pipe:
    class Valves(BaseModel):
        BASE_MODEL_ID: str = Field(
            default="deepseek-v4-flash", description="Open WebUI中的基础模型ID"
        )
        TOP_K: int = Field(default=5, ge=1, le=12, description="课程知识库检索数量")
        MIN_SCORE: float = Field(
            default=0.0,
            ge=0.0,
            le=1.0,
            description="融合排序归一化分数下限（不是向量相似度阈值）",
        )
        BM25_WEIGHT: float = Field(
            default=0.3,
            ge=0.0,
            le=1.0,
            description="混合检索中的BM25权重；其余权重用于向量检索",
        )

    def __init__(self) -> None:
        self.valves = self.Valves()

    async def pipe(
        self,
        body: dict[str, Any],
        __request__: Any,
        __user__: dict[str, Any] | UserModel,
        __event_emitter__: Any = None,
        __task__: Any = None,
    ) -> str:
        user = UserModel(**__user__) if isinstance(__user__, dict) else __user__
        messages = list(body.get("messages") or [])
        if __task__ is not None:
            return await invoke_base_model(
                __request__,
                user,
                model_id=self.valves.BASE_MODEL_ID,
                messages=messages,
                temperature=0.2,
            )

        pipe_model = str(body.get("model") or "")
        if (
            self.valves.BASE_MODEL_ID == pipe_model
            or self.valves.BASE_MODEL_ID.startswith("python_course_langgraph")
        ):
            raise RuntimeError("LangGraph基础模型不能指向课程Pipe自身")
        if not any(message.get("role") == "system" for message in messages):
            messages.insert(
                0, {"role": "system", "content": load_course_system_prompt()}
            )

        runtime = CourseAgentRuntime(
            request=__request__,
            user=user,
            data_dir=Path(DATA_DIR),
            base_model_id=self.valves.BASE_MODEL_ID,
            top_k=self.valves.TOP_K,
            min_score=self.valves.MIN_SCORE,
            bm25_weight=self.valves.BM25_WEIGHT,
            event_emitter=__event_emitter__,
        )
        graph = build_course_agent_graph(runtime)
        result = await graph.ainvoke({"messages": messages})
        return result.get("final_answer") or "课程智能体没有生成有效回答。"
