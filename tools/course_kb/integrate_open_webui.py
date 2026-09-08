from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

CORE_KNOWLEDGE_NAME = "Python课程知识库（优化版）"
SOLUTION_KNOWLEDGE_NAME = "Python课程参考答案（受控）"
ASSISTANT_ID = "python-course-ai-optimized"
ASSISTANT_NAME = "Python程序设计基础 AI 助教（优化版）"
COURSE_TOOL_ID = "python_course_learning"
LANGGRAPH_PIPE_ID = "python_course_langgraph"
PUBLIC_READ_GRANT = {
    "principal_type": "user",
    "principal_id": "*",
    "permission": "read",
}


def request_json(
    base_url: str,
    token: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    allow_not_found: bool = False,
) -> Any:
    data = (
        None
        if payload is None
        else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    )
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=data,
        method=method,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            body = response.read()
            return json.loads(body.decode("utf-8")) if body else None
    except urllib.error.HTTPError as exc:
        if allow_not_found and exc.code == 404:
            return None
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Open WebUI API {method} {path} failed ({exc.code}): {body}"
        ) from exc


def local_admin_token(data_dir: Path, secret_file: Path) -> str:
    import jwt

    db_path = data_dir / "webui.db"
    if not db_path.is_file():
        raise FileNotFoundError(f"Open WebUI database not found: {db_path}")
    with sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True) as connection:
        row = connection.execute(
            "SELECT id FROM user WHERE role='admin' ORDER BY created_at LIMIT 1"
        ).fetchone()
    if not row:
        raise RuntimeError("No Open WebUI admin user was found")
    secret = secret_file.read_text(encoding="ascii").strip()
    if not secret:
        raise RuntimeError(f"Open WebUI secret is empty: {secret_file}")
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "id": row[0],
            "iat": now,
            "exp": now + timedelta(minutes=20),
            "jti": f"course-kb-{time.time_ns()}",
        },
        secret,
        algorithm="HS256",
    )


def find_exact_knowledge(base_url: str, token: str, name: str) -> dict[str, Any] | None:
    query = urllib.parse.urlencode({"query": name, "source": "external", "page": 1})
    response = request_json(base_url, token, "GET", f"/api/v1/knowledge/search?{query}")
    return next(
        (item for item in response.get("items", []) if item.get("name") == name), None
    )


def source_payload(
    name: str,
    description: str,
    endpoint: str,
    collection: str,
    test_query: str,
    access_grants: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "connection": {
            "name": f"{name} - 本地Chroma",
            "provider": "chroma",
            "endpoint": endpoint,
            "auth_config": {},
            "config": {"timeout": 60},
            "capabilities": {"retrieve": True},
            "enabled": True,
        },
        "source": {
            "type": "collection",
            "name": collection,
            "config": {
                "content_field": "document",
                "metadata_field": "metadata",
                "document_id_field": "file_id",
            },
        },
        "access_grants": access_grants or [],
        "test_query": test_query,
        "test_count": 5,
    }


def upsert_external_knowledge(
    base_url: str,
    token: str,
    name: str,
    description: str,
    endpoint: str,
    collection: str,
    test_query: str,
    access_grants: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    payload = source_payload(
        name, description, endpoint, collection, test_query, access_grants
    )
    existing = find_exact_knowledge(base_url, token, name)
    if existing:
        result = request_json(
            base_url,
            token,
            "PATCH",
            f"/api/v1/knowledge/external/source/{existing['id']}",
            payload,
        )
        print(f"Updated external knowledge: {name} ({result['id']})")
        return result
    result = request_json(
        base_url, token, "POST", "/api/v1/knowledge/external/source/create", payload
    )
    print(f"Created external knowledge: {name} ({result['id']})")
    return result


def upsert_course_tool(base_url: str, token: str, content: str) -> dict[str, Any]:
    payload = {
        "id": COURSE_TOOL_ID,
        "name": "Python课程学习工具",
        "content": content,
        "meta": {
            "description": "查询课程章节目录、列出章节资料，并从指定章节抽取练习题材料。",
        },
        "access_grants": [PUBLIC_READ_GRANT],
    }
    existing = request_json(
        base_url,
        token,
        "GET",
        f"/api/v1/tools/id/{COURSE_TOOL_ID}",
        allow_not_found=True,
    )
    if existing:
        result = request_json(
            base_url,
            token,
            "POST",
            f"/api/v1/tools/id/{COURSE_TOOL_ID}/update",
            payload,
        )
        print(f"Updated course tool: {result['name']} ({result['id']})")
        return result
    result = request_json(base_url, token, "POST", "/api/v1/tools/create", payload)
    print(f"Created course tool: {result['name']} ({result['id']})")
    return result


def upsert_langgraph_pipe(base_url: str, token: str, content: str) -> dict[str, Any]:
    payload = {
        "id": LANGGRAPH_PIPE_ID,
        "name": "Python程序设计基础 AI 助教（LangGraph）",
        "content": content,
        "meta": {
            "description": "使用LangGraph显式编排课程检索、章节查询、练习生成、答案分析和引用校验。",
        },
    }
    functions = request_json(base_url, token, "GET", "/api/v1/functions/") or []
    existing = next(
        (item for item in functions if item.get("id") == LANGGRAPH_PIPE_ID), None
    )
    if existing:
        result = request_json(
            base_url,
            token,
            "POST",
            f"/api/v1/functions/id/{LANGGRAPH_PIPE_ID}/update",
            payload,
        )
        print(f"Updated LangGraph pipe: {result['name']} ({result['id']})")
    else:
        result = request_json(
            base_url, token, "POST", "/api/v1/functions/create", payload
        )
        print(f"Created LangGraph pipe: {result['name']} ({result['id']})")
    if not result.get("is_active", False):
        result = request_json(
            base_url,
            token,
            "POST",
            f"/api/v1/functions/id/{LANGGRAPH_PIPE_ID}/toggle",
        )
        print(f"Activated LangGraph pipe: {result['name']} ({result['id']})")
    request_json(base_url, token, "GET", "/api/models?refresh=true")
    return result


def upsert_assistant(
    base_url: str,
    token: str,
    base_model_id: str,
    knowledge: dict[str, Any],
    prompt: str,
) -> dict[str, Any]:
    payload = {
        "id": ASSISTANT_ID,
        "base_model_id": base_model_id,
        "name": ASSISTANT_NAME,
        "params": {"system": prompt, "temperature": 0.2},
        "meta": {
            "profile_image_url": "/static/favicon.png",
            "description": "按章节检索讲义、大纲、习题题目和示例代码的课程助教；默认不读取参考答案库。",
            "knowledge": [
                {
                    "id": knowledge["id"],
                    "name": knowledge["name"],
                    "type": "collection",
                    "description": knowledge.get("description") or knowledge["name"],
                }
            ],
            "toolIds": [COURSE_TOOL_ID],
            "agent": {
                "version": "1.0.0",
                "strategy": "open-webui-native-tool-calling",
                "knowledge_policy": "core-only-by-default",
            },
            "capabilities": {
                "file_context": True,
                "file_upload": True,
                "web_search": False,
                "citations": True,
                "status_updates": True,
                "builtin_tools": True,
            },
            "tags": [{"name": "课程助教"}, {"name": "Python"}],
        },
        "access_grants": [PUBLIC_READ_GRANT],
        "is_active": True,
    }
    query = urllib.parse.urlencode({"id": ASSISTANT_ID})
    existing = request_json(
        base_url,
        token,
        "GET",
        f"/api/v1/models/model?{query}",
        allow_not_found=True,
    )
    if existing:
        result = request_json(
            base_url, token, "POST", "/api/v1/models/model/update", payload
        )
        print(f"Updated assistant model: {ASSISTANT_NAME} ({ASSISTANT_ID})")
        return result
    result = request_json(base_url, token, "POST", "/api/v1/models/create", payload)
    print(f"Created assistant model: {ASSISTANT_NAME} ({ASSISTANT_ID})")
    return result


def main(argv: list[str] | None = None) -> int:
    project_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Register the optimized course KB and assistant in Open WebUI"
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--base-model-id", default="deepseek-v4-flash")
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
    parser.add_argument(
        "--token", default=None, help="Optional existing Open WebUI admin token"
    )
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir).resolve()
    active_path = data_dir / "course_kb" / "active.json"
    if not active_path.is_file():
        print(f"Knowledge build manifest not found: {active_path}", file=sys.stderr)
        return 1
    active = json.loads(active_path.read_text(encoding="utf-8"))
    vector_path = Path(active["vector_path"])
    if not vector_path.is_absolute():
        vector_path = active_path.parent / vector_path
    endpoint = str(vector_path.resolve())
    token = args.token or local_admin_token(data_dir, Path(args.secret_file).resolve())

    core = upsert_external_knowledge(
        args.base_url,
        token,
        CORE_KNOWLEDGE_NAME,
        "按第1—15章组织的课程大纲、讲义、习题题目和Python示例代码。",
        endpoint,
        active["core_collection"],
        "第6章函数的参数传递方式有哪些？",
        [PUBLIC_READ_GRANT],
    )
    upsert_external_knowledge(
        args.base_url,
        token,
        SOLUTION_KNOWLEDGE_NAME,
        "独立保存教材习题答案，不默认绑定课程助教，供教师按需选择。",
        endpoint,
        active["solutions_collection"],
        "第3章程序控制结构习题的参考答案",
    )

    tool_path = project_root / "tools" / "course_agent" / "course_learning_tools.py"
    tool = upsert_course_tool(
        args.base_url, token, tool_path.read_text(encoding="utf-8")
    )

    pipe_path = project_root / "tools" / "course_agent" / "langgraph_pipe.py"
    langgraph_pipe = upsert_langgraph_pipe(
        args.base_url, token, pipe_path.read_text(encoding="utf-8")
    )

    prompt_path = Path(__file__).with_name("assistant_prompt.txt")
    assistant = upsert_assistant(
        args.base_url,
        token,
        args.base_model_id,
        core,
        prompt_path.read_text(encoding="utf-8").strip(),
    )
    print(
        json.dumps(
            {
                "build_id": active["build_id"],
                "core_knowledge_id": core["id"],
                "course_tool_id": tool["id"],
                "langgraph_pipe_id": langgraph_pipe["id"],
                "langgraph_pipe_active": langgraph_pipe["is_active"],
                "assistant_id": assistant["id"],
                "assistant_name": assistant["name"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
