import json
import sqlite3

import pytest

from tools.course_agent.course_learning_tools import Tools, _normalize_resource_type


def create_catalog(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    build_dir = data_dir / "course_kb" / "builds" / "test-v1"
    vector_path = build_dir / "vector_db"
    vector_path.mkdir(parents=True)
    (data_dir / "course_kb" / "active.json").write_text(
        json.dumps({"build_id": "test-v1", "vector_path": "builds/test-v1/vector_db"}),
        encoding="utf-8",
    )
    with sqlite3.connect(build_dir / "catalog.sqlite3") as connection:
        connection.executescript("""
            CREATE TABLE source_file (
                relative_path TEXT, resource_type TEXT, parse_status TEXT,
                issue TEXT, chapter_no INTEGER
            );
            CREATE TABLE chunk (
                file_id TEXT, chapter_no INTEGER, resource_type TEXT,
                collection_role TEXT
            );
            """)
        connection.execute(
            "INSERT INTO source_file VALUES (?, ?, ?, ?, ?)",
            ("第06章/示例代码/demo.py", "code", "completed", None, 6),
        )
        connection.execute(
            "INSERT INTO chunk VALUES (?, ?, ?, ?)", ("file-1", 6, "code", "core")
        )
    monkeypatch.setenv("DATA_DIR", str(data_dir))


def test_resource_type_aliases_and_validation() -> None:
    assert _normalize_resource_type("讲义") == "lecture"
    assert _normalize_resource_type("exercise_question") == "exercise_question"
    with pytest.raises(ValueError, match="不支持的资料类型"):
        _normalize_resource_type("答案")


def test_chapter_material_query_uses_catalog(tmp_path, monkeypatch) -> None:
    create_catalog(tmp_path, monkeypatch)
    result = json.loads(Tools().get_chapter_materials(6, "代码"))
    assert result["build_id"] == "test-v1"
    assert result["chapter_title"] == "函数"
    assert result["chunk_counts"] == {"code": 1}
    assert result["materials"][0]["source_path"].endswith("demo.py")
    assert "不返回参考答案" in result["answer_policy"]


def test_practice_input_validation() -> None:
    with pytest.raises(ValueError, match="1到15"):
        Tools().sample_chapter_exercises(0)
    with pytest.raises(ValueError, match="1到5"):
        Tools().sample_chapter_exercises(6, count=6)
