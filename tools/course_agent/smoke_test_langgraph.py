from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    project_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(project_root / "tools" / "course_kb"))
    from integrate_open_webui import LANGGRAPH_PIPE_ID, local_admin_token, request_json

    parser = argparse.ArgumentParser(
        description="Run a live smoke test for the LangGraph course assistant"
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
    token = args.token or local_admin_token(data_dir, Path(args.secret_file).resolve())

    def chat(content: str | list[dict[str, str]]) -> tuple[str, dict]:
        messages = content if isinstance(content, list) else [{"role": "user", "content": content}]
        response = request_json(
            args.base_url,
            token,
            "POST",
            "/api/chat/completions",
            {
                "model": LANGGRAPH_PIPE_ID,
                "messages": messages,
                "stream": False,
            },
        )
        choices = response.get("choices") or []
        answer = (
            (choices[0].get("message") or {}).get("content") if choices else ""
        ) or ""
        return answer, response

    chapter_answer, chapter_response = chat(
        "第6章叫什么？其中示例代码有多少个知识块？只报告课程目录查询结果。"
    )
    if "函数" not in chapter_answer or "17" not in chapter_answer:
        print(
            json.dumps(chapter_response, ensure_ascii=False, indent=2), file=sys.stderr
        )
        raise RuntimeError("LangGraph智能体未返回第6章名称和17个代码知识块")

    knowledge_answer, knowledge_response = chat(
        "第6章中函数的参数传递方式有哪些？请依据课程资料回答并给出来源。"
    )
    if (
        "参数" not in knowledge_answer
        or "来源" not in knowledge_answer
        or "第06章" not in knowledge_answer
    ):
        print(
            json.dumps(knowledge_response, ensure_ascii=False, indent=2),
            file=sys.stderr,
        )
        raise RuntimeError("LangGraph智能体未完成核心知识库检索与来源引用")

    function_answer, function_response = chat("在Python中，什么是函数？")
    if (
        "函数" not in function_answer
        or "def" not in function_answer
        or "第06章" not in function_answer
        or "无法确认" in function_answer
    ):
        print(
            json.dumps(function_response, ensure_ascii=False, indent=2),
            file=sys.stderr,
        )
        raise RuntimeError("LangGraph智能体未召回第6章函数基本定义及调用")

    keywords_answer, keywords_response = chat("python中所有的关键字")
    expected_keywords = (
        "and",
        "assert",
        "async",
        "await",
        "break",
        "class",
        "continue",
        "def",
        "elif",
        "except",
        "False",
        "global",
        "import",
        "lambda",
        "nonlocal",
        "None",
        "raise",
        "return",
        "True",
        "while",
        "yield",
    )
    if (
        "无法确认" in keywords_answer
        or "第02章" not in keywords_answer
        or any(keyword not in keywords_answer for keyword in expected_keywords)
    ):
        print(
            json.dumps(keywords_response, ensure_ascii=False, indent=2),
            file=sys.stderr,
        )
        raise RuntimeError("LangGraph智能体未稳定召回第2章中的完整关键字表")

    follow_up_answer, follow_up_response = chat(
        [
            {"role": "user", "content": "列表和元组最主要的区别是什么？"},
            {"role": "assistant", "content": "列表可变，而元组不可变。"},
            {"role": "user", "content": "那后者为什么不能修改？"},
        ]
    )
    if "元组" not in follow_up_answer or any(
        marker in follow_up_answer
        for marker in ("无法判断", "无法确认", "无法确定后者", "正则表达式")
    ):
        print(json.dumps(follow_up_response, ensure_ascii=False, indent=2), file=sys.stderr)
        raise RuntimeError("LangGraph智能体未正确解析多轮追问中的“后者”")

    pickle_answer, pickle_response = chat(
        "请结合课程资料说明pickle.dumps和pickle.loads如何配合完成序列化与反序列化。"
    )
    if (
        "dumps" not in pickle_answer
        or "loads" not in pickle_answer
        or "pickle.loads(" not in pickle_answer
        or "第10章" not in pickle_answer.replace("第10 章", "第10章")
        or any(marker in pickle_answer for marker in ("没有给出 `pickle.loads`", "无法完全确认"))
    ):
        print(json.dumps(pickle_response, ensure_ascii=False, indent=2), file=sys.stderr)
        raise RuntimeError("LangGraph智能体未召回pickle流程的相邻知识块")

    print(
        json.dumps(
            {
                "status": "passed",
                "model": LANGGRAPH_PIPE_ID,
                "chapter_query": chapter_answer,
                "knowledge_query": knowledge_answer,
                "function_definition_query": function_answer,
                "keywords_query": keywords_answer,
                "follow_up_query": follow_up_answer,
                "pickle_query": pickle_answer,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
