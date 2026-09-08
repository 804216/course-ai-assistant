from __future__ import annotations

import argparse
import inspect
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _assistant_message(response: dict[str, Any]) -> dict[str, Any]:
    choices = response.get("choices") or []
    if not choices or not isinstance(choices[0].get("message"), dict):
        raise RuntimeError("模型响应中缺少 assistant message")
    return choices[0]["message"]


def _tool_registry() -> dict[str, Any]:
    from tools.chapter_query_tool import Tools as ChapterTools
    from tools.course_agent.course_learning_tools import Tools as CourseTools
    from tools.quiz_tools import Tools as QuizTools

    return {
        "python_course_learning": CourseTools(),
        "chapter_query": ChapterTools(),
        "quiz": QuizTools(),
    }


def _resolve_tool(
    name: str, registry: dict[str, Any]
) -> tuple[str, str, Any]:
    for tool_id, toolbox in registry.items():
        candidate = name
        prefix = f"{tool_id}_"
        if candidate.startswith(prefix):
            candidate = candidate[len(prefix) :]
        function = getattr(toolbox, candidate, None)
        if callable(function) and not candidate.startswith("_"):
            return tool_id, candidate, function
    raise RuntimeError(f"没有找到模型请求的工具函数：{name}")


def _run_tool_call(
    tool_call: dict[str, Any], registry: dict[str, Any]
) -> tuple[dict[str, Any], str]:
    definition = tool_call.get("function") or {}
    requested_name = str(definition.get("name") or "")
    try:
        arguments = json.loads(definition.get("arguments") or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"工具参数不是有效 JSON：{requested_name}") from exc
    tool_id, function_name, function = _resolve_tool(requested_name, registry)
    result = function(**arguments)
    if inspect.isawaitable(result):
        raise RuntimeError(f"对比测试不支持异步工具：{requested_name}")
    content = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
    return {
        "tool_id": tool_id,
        "function": function_name,
        "arguments": arguments,
    }, content


def _model_tool_ids(
    base_url: str, token: str, model_id: str
) -> list[str]:
    from integrate_open_webui import request_json

    import urllib.parse

    query = urllib.parse.urlencode({"id": model_id})
    model = request_json(
        base_url,
        token,
        "GET",
        f"/api/v1/models/model?{query}",
        allow_not_found=True,
    )
    if not model:
        return []
    meta = model.get("meta") or {}
    return list(meta.get("toolIds") or [])


def run_question(
    base_url: str,
    token: str,
    model_id: str,
    question: str,
    tool_ids: list[str],
    registry: dict[str, Any],
) -> tuple[str, list[dict[str, Any]]]:
    from integrate_open_webui import request_json

    messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
    executed: list[dict[str, Any]] = []
    for _ in range(5):
        payload: dict[str, Any] = {
            "model": model_id,
            "messages": messages,
            "stream": False,
        }
        if tool_ids:
            payload["tool_ids"] = tool_ids
        response = request_json(
            base_url,
            token,
            "POST",
            "/api/chat/completions",
            payload,
        )
        assistant = _assistant_message(response)
        tool_calls = assistant.get("tool_calls") or []
        if not tool_calls:
            return str(assistant.get("content") or ""), executed
        messages.append(
            {
                "role": "assistant",
                "content": assistant.get("content") or "",
                "tool_calls": tool_calls,
            }
        )
        for tool_call in tool_calls:
            execution, content = _run_tool_call(tool_call, registry)
            executed.append(execution)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.get("id", ""),
                    "name": (tool_call.get("function") or {}).get("name", ""),
                    "content": content,
                }
            )
    raise RuntimeError("连续五轮工具调用后模型仍未返回最终答案")


def main(argv: list[str] | None = None) -> int:
    project_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(project_root))
    sys.path.insert(0, str(project_root / "tools" / "course_kb"))

    from integrate_open_webui import local_admin_token

    parser = argparse.ArgumentParser(
        description="Run the same acceptance questions against a comparison model"
    )
    parser.add_argument("--model", default="python-ai-")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument(
        "--source",
        default=str(
            project_root
            / "open-webui"
            / "local-deploy"
            / "tmp"
            / "agent_acceptance_raw.json"
        ),
    )
    parser.add_argument(
        "--output",
        default=str(
            project_root
            / "open-webui"
            / "local-deploy"
            / "tmp"
            / "agent_acceptance_before_raw.json"
        ),
    )
    parser.add_argument(
        "--data-dir",
        default=str(project_root / "open-webui" / "local-deploy" / "data"),
    )
    parser.add_argument(
        "--secret-file",
        default=str(
            project_root / "open-webui" / "local-deploy" / "webui_secret_key.txt"
        ),
    )
    parser.add_argument("--token", default=None)
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir).resolve()
    os.environ["DATA_DIR"] = str(data_dir)
    source = json.loads(Path(args.source).read_text(encoding="utf-8"))
    token = args.token or local_admin_token(data_dir, Path(args.secret_file).resolve())
    tool_ids = _model_tool_ids(args.base_url, token, args.model)
    registry = _tool_registry()
    started_at = datetime.now(timezone.utc).isoformat()
    results: dict[str, Any] = {}

    for index, source_result in source["results"].items():
        question = source_result["question"]
        print(f"[{index}/{len(source['results'])}] {source_result['category']}", flush=True)
        started = time.perf_counter()
        try:
            answer, tool_calls = run_question(
                args.base_url,
                token,
                args.model,
                question,
                tool_ids,
                registry,
            )
            error = None
        except Exception as exc:
            answer = ""
            tool_calls = []
            error = f"{type(exc).__name__}: {exc}"
        results[index] = {
            "category": source_result["category"],
            "question": question,
            "answer": answer,
            "elapsed_seconds": round(time.perf_counter() - started, 2),
            "tool_calls": tool_calls,
            "error": error,
        }
        output = {
            "model": args.model,
            "comparison_source": str(Path(args.source).resolve()),
            "started_at": started_at,
            "tool_ids": tool_ids,
            "results": results,
            "completed_at": None,
        }
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(
            json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    output["completed_at"] = datetime.now(timezone.utc).isoformat()
    Path(args.output).write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Saved: {Path(args.output).resolve()}")
    return 0 if all(item["error"] is None for item in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
