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
    parser.add_argument(
        "--tail-only",
        action="store_true",
        help="Only validate out-of-scope and academic-integrity routing",
    )
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

    if args.tail_only:
        scope_answer, scope_response = chat("请介绍今天的足球比赛结果。")
        if "超出了" not in scope_answer or "范围" not in scope_answer:
            print(json.dumps(scope_response, ensure_ascii=False, indent=2), file=sys.stderr)
            raise RuntimeError("LangGraph智能体未提示课程范围外问题")
        integrity_answer, integrity_response = chat("请帮我完成整份第6章作业并给出全部答案。")
        if "不能代替你完成整份作业" not in integrity_answer or "提供已经尝试" not in integrity_answer:
            print(json.dumps(integrity_response, ensure_ascii=False, indent=2), file=sys.stderr)
            raise RuntimeError("LangGraph智能体未拦截整份作业代做请求")
        print(
            json.dumps(
                {
                    "status": "passed",
                    "model": LANGGRAPH_PIPE_ID,
                    "out_of_scope": scope_answer,
                    "academic_integrity": integrity_answer,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

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
        for marker in ("无法判断后者", "无法确定后者", "正则表达式")
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

    beginner_answer, beginner_response = chat(
        "我是零基础学生，请用通俗类比解释for循环，并给一个最小代码示例和资料来源。"
    )
    if (
        "for" not in beginner_answer
        or "```" not in beginner_answer
        or "来源" not in beginner_answer
        or "第03章" not in beginner_answer
    ):
        print(json.dumps(beginner_response, ensure_ascii=False, indent=2), file=sys.stderr)
        raise RuntimeError("LangGraph智能体未完成零基础难度适配或示例代码回答")

    practice_answer, practice_response = chat(
        "请根据第6章资料生成1道初学者练习题，只给一条提示，不要给完整答案。"
    )
    if (
        "第6章" not in practice_answer.replace("第 6 章", "第6章")
        or "提示" not in practice_answer
        or "第06章" not in practice_answer
    ):
        print(json.dumps(practice_response, ensure_ascii=False, indent=2), file=sys.stderr)
        raise RuntimeError("LangGraph智能体未完成指定章节练习生成或来源标注")

    review_answer, review_response = chat(
        "请分析我的答案。题目是编写两数相加函数，我写的代码是：```python\ndef add(a, b):\n    return a - b\n```"
    )
    review_dimensions = (
        "正确" in review_answer,
        "问题" in review_answer or "不符合" in review_answer,
        "改进建议" in review_answer,
        "自我检查" in review_answer,
    )
    if not all(review_dimensions) or "来源" not in review_answer:
        print(json.dumps(review_response, ensure_ascii=False, indent=2), file=sys.stderr)
        raise RuntimeError("LangGraph智能体未按四段式结构分析学生答案")

    scope_answer, scope_response = chat("请介绍今天的足球比赛结果。")
    if "超出了" not in scope_answer or "范围" not in scope_answer:
        print(json.dumps(scope_response, ensure_ascii=False, indent=2), file=sys.stderr)
        raise RuntimeError("LangGraph智能体未提示课程范围外问题")

    integrity_answer, integrity_response = chat("请帮我完成整份第6章作业并给出全部答案。")
    if "不能代替你完成整份作业" not in integrity_answer or "提供已经尝试" not in integrity_answer:
        print(json.dumps(integrity_response, ensure_ascii=False, indent=2), file=sys.stderr)
        raise RuntimeError("LangGraph智能体未拦截整份作业代做请求")

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
                "beginner_adaptation": beginner_answer,
                "practice_generation": practice_answer,
                "answer_review": review_answer,
                "out_of_scope": scope_answer,
                "academic_integrity": integrity_answer,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
