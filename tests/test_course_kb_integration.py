from tools.course_kb import integrate_open_webui as integration


def test_workspace_tool_ids_are_complete_and_stable() -> None:
    assert integration.ASSISTANT_TOOL_IDS == [
        "python_course_learning",
        "chapter_query",
        "quiz",
    ]


def test_upsert_tool_creates_requested_tool(monkeypatch) -> None:
    calls = []

    def fake_request(base_url, token, method, path, payload=None, allow_not_found=False):
        calls.append((method, path, payload, allow_not_found))
        if method == "GET":
            return None
        return payload

    monkeypatch.setattr(integration, "request_json", fake_request)
    result = integration.upsert_tool(
        "http://127.0.0.1:8080",
        "token",
        "quiz",
        "Python课程随机抽题与判分工具",
        "description",
        "class Tools: pass",
    )

    assert result["id"] == "quiz"
    assert result["access_grants"] == [integration.PUBLIC_READ_GRANT]
    assert calls[0][1] == "/api/v1/tools/id/quiz"
    assert calls[1][1] == "/api/v1/tools/create"


def test_assistant_binds_all_registered_tools(monkeypatch) -> None:
    captured = {}

    def fake_request(base_url, token, method, path, payload=None, allow_not_found=False):
        if method == "GET":
            return None
        captured.update(payload)
        return payload

    monkeypatch.setattr(integration, "request_json", fake_request)
    result = integration.upsert_assistant(
        "http://127.0.0.1:8080",
        "token",
        "deepseek-v4-flash",
        {"id": "knowledge-id", "name": "Python课程知识库（优化版）"},
        "system prompt",
        integration.ASSISTANT_TOOL_IDS,
    )

    assert result["meta"]["toolIds"] == integration.ASSISTANT_TOOL_IDS
    assert captured["meta"]["toolIds"] == [
        "python_course_learning",
        "chapter_query",
        "quiz",
    ]
