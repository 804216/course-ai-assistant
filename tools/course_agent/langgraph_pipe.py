"""
title: Python程序设计基础 AI 助教（LangGraph）
author: course-ai-assistant
version: 1.5.0
description: 使用LangGraph编排课程知识检索、章节查询、练习生成和学生答案分析。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from course_agent_langgraph.graph import CourseAgentRuntime, build_course_agent_graph
from course_agent_langgraph.model_gateway import invoke_base_model
from open_webui.env import DATA_DIR
from open_webui.models.users import UserModel


class Pipe:
    class Valves(BaseModel):
        BASE_MODEL_ID: str = Field(
            default="deepseek-v4-flash", description="Open WebUI中的基础模型ID"
        )
        TOP_K: int = Field(
            default=8,
            ge=3,
            le=12,
            description="按问题类型动态选取的最大证据组数量",
        )
        MIN_SCORE: float = Field(
            default=0.0,
            ge=0.0,
            le=1.0,
            description="最终排序分数下限；启用重排时为重排分数，降级时为融合分数",
        )
        BM25_WEIGHT: float = Field(
            default=0.3,
            ge=0.0,
            le=1.0,
            description="混合检索中的BM25权重；其余权重用于向量检索",
        )
        CANDIDATE_K: int = Field(
            default=40,
            ge=20,
            le=80,
            description="向量与BM25融合后送入重排序的最大候选数",
        )
        RERANK_TOP_N: int = Field(
            default=12,
            ge=3,
            le=30,
            description="重排序后参与证据分组和多样化选择的候选数",
        )
        RERANK_MIN_SCORE: float = Field(
            default=0.0,
            ge=0.0,
            le=1.0,
            description="BGE重排序相关性分数下限；0表示不硬过滤",
        )
        EVIDENCE_MIN_SCORE: float = Field(
            default=0.05,
            ge=0.0,
            le=1.0,
            description="证据充分性判断使用的最低重排分数",
        )
        EVIDENCE_MIN_COVERAGE: float = Field(
            default=0.08,
            ge=0.0,
            le=1.0,
            description="查询关键词在证据中的最低覆盖率",
        )

    def __init__(self) -> None:
        self.valves = self.Valves()
        self.graph = build_course_agent_graph()

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
        runtime = CourseAgentRuntime(
            request=__request__,
            user=user,
            data_dir=Path(DATA_DIR),
            base_model_id=self.valves.BASE_MODEL_ID,
            top_k=self.valves.TOP_K,
            min_score=self.valves.MIN_SCORE,
            bm25_weight=self.valves.BM25_WEIGHT,
            candidate_k=self.valves.CANDIDATE_K,
            rerank_top_n=self.valves.RERANK_TOP_N,
            rerank_min_score=self.valves.RERANK_MIN_SCORE,
            evidence_min_score=self.valves.EVIDENCE_MIN_SCORE,
            evidence_min_coverage=self.valves.EVIDENCE_MIN_COVERAGE,
            event_emitter=__event_emitter__,
        )
        result = await self.graph.ainvoke({"messages": messages}, context=runtime)
        return result.get("final_answer") or "课程智能体没有生成有效回答。"
