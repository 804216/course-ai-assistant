from __future__ import annotations

import argparse
import inspect
import json
import os
import sys
from pathlib import Path
from typing import Any


def _message_from_response(response: dict[str, Any]) -> dict[str, Any]:
    choices = response.get("choices") or []
    if not choices or not isinstance(choices[0].get("message"), dict):
        raise RuntimeError(f"模型响应中缺少 assistant message：{response}")
    return choices[0]["message"]


def _run_tool(toolbox: Any, tool_call: dict[str, Any]) -> tuple[str, str]:
    function = tool_call.get("function") or {}
    name = function.get("name", "")
    if not name or name.startswith("_"):
        raise RuntimeError(f"模型返回了无效工具名：{name!r}")
    callable_tool = getattr(toolbox, name, None)
    if not callable(callable_tool):
        raise RuntimeError(f"课程工具中不存在函数：{name}")
    try:
        arguments = json.loads(function.get("arguments") or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"工具 {name} 的参数不是有效 JSON") from exc
    result = callable_tool(**arguments)
    if inspect.isawaitable(result):
        raise RuntimeError(f"冒烟测试暂不支持异步工具：{name}")
    return name, result if isinstance(result, str) else json.dumps(
        result, ensure_ascii=False
    )


def run_tool_protocol(
    base_url: str,
    token: str,
    model: str,
    tool_id: str,
    toolbox: Any,
) -> tuple[str, list[dict[str, Any]]]:
    from integrate_open_webui import request_json

    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": "请调用课程章节资料工具回答：第6章叫什么？其中示例代码有多少个知识块？只报告工具查询到的结果。",
        }
    ]
    executed: list[dict[str, Any]] = []

    for _ in range(3):
        response = request_json(
            base_url,
            token,
            "POST",
            "/api/chat/completions",
            {
                "model": model,
                "messages": messages,
                "tool_ids": [tool_id],
                "stream": False,
            },
        )
        assistant = _message_from_response(response)
        tool_calls = assistant.get("tool_calls") or []
        if not tool_calls:
            return assistant.get("content") or "", executed

        messages.append(
            {
                "role": "assistant",
                "content": assistant.get("content") or "",
                "tool_calls": tool_calls,
            }
        )
        for tool_call in tool_calls:
            name, result = _run_tool(toolbox, tool_call)
            executed.append(
                {
                    "name": name,
                    "arguments": json.loads(
                        tool_call["function"].get("arguments") or "{}"
                    ),
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.get("id", ""),
                    "name": name,
                    "content": result,
                }
            )
    raise RuntimeError("课程智能体连续三轮仍未结束工具调用")


def main(argv: list[str] | None = None) -> int:
    project_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(project_root))
    sys.path.insert(0, str(project_root / "tools" / "course_kb"))
    from integrate_open_webui import COURSE_TOOL_ID, local_admin_token

    from tools.course_agent.course_learning_tools import Tools

    parser = argparse.ArgumentParser(
        description="Run a live tool-calling smoke test for the course assistant"
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument(
        "--data-dir", default=str(project_root / "open-webui" / "local-deploy" / "data")
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
    token = args.token or local_admin_token(data_dir, Path(args.secret_file).resolve())
    content, executed = run_tool_protocol(
        args.base_url,
        token,
        "python-course-ai-optimized",
        COURSE_TOOL_ID,
        Tools(),
    )
    tool_names = {item["name"] for item in executed}
    if "get_chapter_materials" not in tool_names:
        raise RuntimeError(f"模型没有选择章节资料工具：{executed}")
    if "函数" not in content or "17" not in content:
        print(
            json.dumps(
                {"content": content, "executed": executed}, ensure_ascii=False, indent=2
            ),
            file=sys.stderr,
        )
        raise RuntimeError("智能体未根据工具结果回答第6章名称和17个代码知识块")
    print(
        json.dumps(
            {"status": "passed", "content": content, "executed": executed},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
