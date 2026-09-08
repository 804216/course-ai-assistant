from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

from integrate_open_webui import (
    ASSISTANT_ID,
    COURSE_TOOL_ID,
    LANGGRAPH_PIPE_ID,
    local_admin_token,
    request_json,
    source_payload,
)

OLD_KNOWLEDGE_ID = "f65a2503-7504-4bd5-898a-014af306a23c"
OLD_ASSISTANT_ID = "python-ai-"


def json_value(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def test_external_collection(
    base_url: str,
    token: str,
    endpoint: str,
    collection: str,
    query: str,
    chapter_no: int,
) -> dict[str, Any]:
    definition = source_payload("validation", "", endpoint, collection, query)
    result = request_json(
        base_url,
        token,
        "POST",
        "/api/v1/knowledge/external/source/test",
        {
            "connection": definition["connection"],
            "source": definition["source"],
            "query": query,
            "count": 5,
        },
    )
    documents = result.get("documents") or []
    metadatas = result.get("metadatas") or []
    if not documents:
        raise RuntimeError(f"检索未返回结果：{collection}")
    if any(metadata.get("chapter_no") != chapter_no for metadata in metadatas):
        raise RuntimeError(f"显式章节检索返回了其他章节：{collection}")
    return {
        "documents": len(documents),
        "chapters": sorted({metadata.get("chapter_no") for metadata in metadatas}),
        "sources": sorted({metadata.get("source") for metadata in metadatas}),
    }


def validate(args: argparse.Namespace) -> dict[str, Any]:
    project_root = Path(__file__).resolve().parents[2]
    data_dir = Path(args.data_dir).resolve()
    active = json.loads(
        (data_dir / "course_kb" / "active.json").read_text(encoding="utf-8")
    )
    vector_path = Path(active["vector_path"])
    if not vector_path.is_absolute():
        vector_path = data_dir / "course_kb" / vector_path
    active["vector_path"] = str(vector_path.resolve())
    build_dir = data_dir / "course_kb" / "builds" / active["build_id"]

    with sqlite3.connect(
        f"file:{(build_dir / 'catalog.sqlite3').as_posix()}?mode=ro", uri=True
    ) as catalog:
        build_status = catalog.execute(
            "SELECT status FROM build WHERE id=?", (active["build_id"],)
        ).fetchone()[0]
        source_status = dict(
            catalog.execute(
                "SELECT parse_status, COUNT(*) FROM source_file GROUP BY parse_status"
            )
        )
        source_count = catalog.execute("SELECT COUNT(*) FROM source_file").fetchone()[0]
        source_types = dict(
            catalog.execute(
                "SELECT resource_type, COUNT(*) FROM source_file GROUP BY resource_type"
            )
        )
        source_extensions = dict(
            catalog.execute(
                "SELECT extension, COUNT(*) FROM source_file GROUP BY extension"
            )
        )
        chapter_groups = dict(
            catalog.execute(
                "SELECT chapter_no, COUNT(*) FROM source_file GROUP BY chapter_no ORDER BY chapter_no"
            )
        )
        unclassified_sources = catalog.execute(
            "SELECT COUNT(*) FROM source_file WHERE chapter_no IS NULL"
        ).fetchone()[0]
        chunk_roles = dict(
            catalog.execute(
                "SELECT collection_role, COUNT(*) FROM chunk GROUP BY collection_role"
            )
        )
        asset_count = catalog.execute("SELECT COUNT(*) FROM asset").fetchone()[0]
        catalog_chunks = {
            row[0]: {"text_hash": row[1], "role": row[2]}
            for row in catalog.execute(
                "SELECT id, text_hash, collection_role FROM chunk"
            )
        }
        duplicate_hashes = catalog.execute(
            "SELECT COUNT(*) FROM (SELECT text_hash FROM chunk GROUP BY text_hash HAVING COUNT(*) > 1)"
        ).fetchone()[0]
    if build_status != "ready" or source_status.get("failed", 0):
        raise RuntimeError(
            f"目录数据库状态异常：build={build_status}, sources={source_status}"
        )

    required_core_types = {"lecture", "exercise_question", "code"}
    available_core_types = set(source_types) - {"exercise_answer"}
    if source_count < 8:
        raise RuntimeError(f"课程资料文件不足8个：{source_count}")
    if len(available_core_types) < 3 or not required_core_types.issubset(available_core_types):
        raise RuntimeError(f"课程资料类型不足或缺少讲义/习题/代码：{sorted(available_core_types)}")
    if unclassified_sources or len(chapter_groups) < 2:
        raise RuntimeError(
            f"课程资料未按章节或模块完整分类：unclassified={unclassified_sources}, groups={len(chapter_groups)}"
        )

    prompt = (project_root / "tools" / "course_kb" / "assistant_prompt.txt").read_text(
        encoding="utf-8"
    )
    prompt_clauses = {
        "identity": "AI 助教",
        "course_scope": "课程范围",
        "answer_format": "默认回答结构",
        "citation": "引用必须",
        "academic_integrity": "不得直接代替学生完成整份作业",
        "uncertainty": "根据现有课程资料无法确认",
    }
    missing_prompt_clauses = [
        name for name, marker in prompt_clauses.items() if marker not in prompt
    ]
    if missing_prompt_clauses:
        raise RuntimeError(f"课程助教系统提示词缺少验收条款：{missing_prompt_clauses}")

    import chromadb

    chroma = chromadb.PersistentClient(path=active["vector_path"])
    collections = {
        "core": chroma.get_collection(active["core_collection"]),
        "solutions": chroma.get_collection(active["solutions_collection"]),
    }
    vector_counts = {role: collection.count() for role, collection in collections.items()}
    if vector_counts != {
        "core": active["core_chunks"],
        "solutions": active["solution_chunks"],
    }:
        raise RuntimeError(f"向量数量不一致：{vector_counts}")

    vector_ids: set[str] = set()
    missing_metadata: list[str] = []
    empty_documents: list[str] = []
    extraction_artifacts: list[str] = []
    section_title_count = 0
    for role, collection in collections.items():
        payload = collection.get(include=["documents", "metadatas"])
        ids = list(payload.get("ids") or [])
        documents = list(payload.get("documents") or [])
        metadatas = list(payload.get("metadatas") or [])
        vector_ids.update(ids)
        for index, item_id in enumerate(ids):
            document = documents[index] if index < len(documents) else ""
            metadata = dict(metadatas[index] or {}) if index < len(metadatas) else {}
            if not document.strip():
                empty_documents.append(item_id)
            required = ("file_id", "text_hash", "source", "ordinal", "build_id")
            if any(key not in metadata for key in required) or metadata.get("build_id") != active["build_id"]:
                missing_metadata.append(item_id)
            if metadata.get("section_title"):
                section_title_count += 1
            if "'await" in document or "'in  while" in document:
                extraction_artifacts.append(item_id)
            catalog_row = catalog_chunks.get(item_id)
            if not catalog_row or catalog_row["role"] != role or catalog_row["text_hash"] != metadata.get("text_hash"):
                missing_metadata.append(item_id)
    if vector_ids != set(catalog_chunks):
        raise RuntimeError("目录数据库与Chroma中的知识块ID不一致")
    if duplicate_hashes or empty_documents or missing_metadata or extraction_artifacts:
        raise RuntimeError(
            "知识块完整性异常："
            f"duplicate_hashes={duplicate_hashes}, empty={len(empty_documents)}, "
            f"metadata={len(set(missing_metadata))}, artifacts={len(extraction_artifacts)}"
        )

    db_path = data_dir / "webui.db"
    with sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True) as database:
        optimized_knowledge = database.execute(
            "SELECT id, name, meta FROM knowledge WHERE name IN (?, ?)",
            ("Python课程知识库（优化版）", "Python课程参考答案（受控）"),
        ).fetchall()
        assistant = database.execute(
            "SELECT id, name, base_model_id, meta FROM model WHERE id=?",
            (ASSISTANT_ID,),
        ).fetchone()
        course_tool = database.execute(
            "SELECT id, name, specs FROM tool WHERE id=?", (COURSE_TOOL_ID,)
        ).fetchone()
        langgraph_pipe = database.execute(
            "SELECT id, name, type, is_active FROM function WHERE id=?",
            (LANGGRAPH_PIPE_ID,),
        ).fetchone()
        old_knowledge = database.execute(
            "SELECT name FROM knowledge WHERE id=?", (OLD_KNOWLEDGE_ID,)
        ).fetchone()
        old_assistant = database.execute(
            "SELECT name FROM model WHERE id=?", (OLD_ASSISTANT_ID,)
        ).fetchone()
    if (
        len(optimized_knowledge) != 2
        or not assistant
        or not course_tool
        or not langgraph_pipe
    ):
        raise RuntimeError("优化知识库、助教、课程工具或LangGraph Pipe尚未完整注册")
    if langgraph_pipe[2] != "pipe" or not langgraph_pipe[3]:
        raise RuntimeError(
            f"LangGraph Pipe状态异常：type={langgraph_pipe[2]}, active={langgraph_pipe[3]}"
        )
    if not old_knowledge or not old_assistant:
        raise RuntimeError("原有知识库或原有助教缺失")

    knowledge_by_name = {
        name: {"id": item_id, "meta": json_value(meta)}
        for item_id, name, meta in optimized_knowledge
    }
    core_id = knowledge_by_name["Python课程知识库（优化版）"]["id"]
    assistant_meta = json_value(assistant[3])
    bound_ids = [item.get("id") for item in assistant_meta.get("knowledge", [])]
    if bound_ids != [core_id]:
        raise RuntimeError(f"助教知识库绑定不符合预期：{bound_ids}")
    if assistant_meta.get("toolIds") != [COURSE_TOOL_ID]:
        raise RuntimeError(f"助教工具绑定不符合预期：{assistant_meta.get('toolIds')}")

    with sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True) as database:
        public_grants = {
            (resource_type, resource_id)
            for resource_type, resource_id in database.execute(
                """
                SELECT resource_type, resource_id FROM access_grant
                WHERE principal_type='user' AND principal_id='*' AND permission='read'
                  AND resource_id IN (?, ?, ?)
                """,
                (ASSISTANT_ID, COURSE_TOOL_ID, core_id),
            ).fetchall()
        }
    expected_public = {
        ("model", ASSISTANT_ID),
        ("tool", COURSE_TOOL_ID),
        ("knowledge", core_id),
    }
    if public_grants != expected_public:
        raise RuntimeError(f"智能体公共只读授权不符合预期：{public_grants}")

    tool_specs = json_value(course_tool[2])
    tool_names = sorted(spec.get("name") for spec in tool_specs)
    expected_tools = [
        "get_chapter_materials",
        "get_course_outline",
        "sample_chapter_exercises",
    ]
    if tool_names != expected_tools:
        raise RuntimeError(f"课程工具函数不符合预期：{tool_names}")

    token = args.token or local_admin_token(data_dir, Path(args.secret_file).resolve())
    health = request_json(args.base_url, token, "GET", "/health")
    models = request_json(args.base_url, token, "GET", "/api/models").get("data", [])
    if ASSISTANT_ID not in {model.get("id") for model in models}:
        raise RuntimeError("优化版助教未出现在前端模型列表中")
    if LANGGRAPH_PIPE_ID not in {model.get("id") for model in models}:
        raise RuntimeError("LangGraph助教未出现在前端模型列表中")
    tool_api = request_json(
        args.base_url, token, "GET", f"/api/v1/tools/id/{COURSE_TOOL_ID}"
    )
    if tool_api.get("id") != COURSE_TOOL_ID:
        raise RuntimeError("课程工具未出现在 Open WebUI 工具接口中")

    import sys

    sys.path.insert(0, str(project_root))
    from tools.course_agent.course_learning_tools import Tools

    course_tools = Tools()
    outline = json.loads(course_tools.get_course_outline())
    materials = json.loads(course_tools.get_chapter_materials(6, "代码"))
    exercises = json.loads(
        course_tools.sample_chapter_exercises(6, count=2, seed=20260904)
    )
    if (
        len(outline.get("chapters", [])) != 16
        or materials.get("chunk_counts", {}).get("code") != 17
    ):
        raise RuntimeError("课程目录工具返回结果不符合预期")
    if exercises.get("count") != 2 or any(
        item.get("source") is None for item in exercises["exercises"]
    ):
        raise RuntimeError("章节练习工具返回结果不符合预期")

    retrieval = {
        "core": test_external_collection(
            args.base_url,
            token,
            active["vector_path"],
            active["core_collection"],
            "第6章函数的参数传递方式有哪些？",
            6,
        ),
        "solutions": test_external_collection(
            args.base_url,
            token,
            active["vector_path"],
            active["solutions_collection"],
            "第3章程序控制结构习题的参考答案",
            3,
        ),
    }
    return {
        "health": health,
        "build_id": active["build_id"],
        "source_status": source_status,
        "course_requirements": {
            "source_files": source_count,
            "minimum_source_files": 8,
            "source_file_requirement_passed": source_count >= 8,
            "resource_types": source_types,
            "core_resource_type_count": len(available_core_types),
            "required_core_types_present": sorted(required_core_types),
            "extensions": source_extensions,
            "chapter_groups": chapter_groups,
            "unclassified_sources": unclassified_sources,
            "system_prompt_clauses": sorted(prompt_clauses),
        },
        "chunk_roles": chunk_roles,
        "asset_count": asset_count,
        "vector_counts": vector_counts,
        "vector_integrity": {
            "catalog_ids_match": True,
            "duplicate_text_hashes": duplicate_hashes,
            "empty_documents": len(empty_documents),
            "missing_or_invalid_metadata": len(set(missing_metadata)),
            "keyword_extraction_artifacts": len(extraction_artifacts),
            "section_titles": section_title_count,
        },
        "retrieval": retrieval,
        "assistant": {
            "id": assistant[0],
            "name": assistant[1],
            "base_model_id": assistant[2],
        },
        "agent_tools": {
            "tool_id": course_tool[0],
            "functions": tool_names,
            "chapter_count": len(outline["chapters"]),
            "chapter_6_code_chunks": materials["chunk_counts"]["code"],
            "sampled_exercises": exercises["count"],
        },
        "langgraph_agent": {
            "id": langgraph_pipe[0],
            "name": langgraph_pipe[1],
            "type": langgraph_pipe[2],
            "active": bool(langgraph_pipe[3]),
        },
        "preserved": {"knowledge": old_knowledge[0], "assistant": old_assistant[0]},
    }


def main(argv: list[str] | None = None) -> int:
    project_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Validate the course knowledge base and Open WebUI integration"
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
    print(json.dumps(validate(args), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
