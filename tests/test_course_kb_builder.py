from pathlib import Path

from tools.course_kb.build_course_kb import (
    chapter_from_path,
    clean_pdf_page_text,
    infer_section_title,
    resource_type_for,
    split_code_lines,
    split_text,
)


def test_chapter_detection_keeps_related_material_together() -> None:
    assert chapter_from_path(Path("讲义/第03章 程序控制结构.pdf")) == 3
    assert chapter_from_path(Path("代码/chapter03/example.py")) == 3
    assert chapter_from_path(Path("课程说明/Python程序设计教学大纲.pdf")) == 0


def test_resource_classification_separates_answers_from_core() -> None:
    assert resource_type_for(Path("习题/第03章题目.pdf")) == "exercise_question"
    assert resource_type_for(Path("习题/第03章答案.pdf")) == "exercise_answer"
    assert resource_type_for(Path("代码/chapter03/example.py")) == "code"
    assert resource_type_for(Path("讲义/第03章.pdf")) == "lecture"


def test_text_split_preserves_overlap_and_size() -> None:
    text = "第一段。\n\n" + "甲" * 80 + "\n\n" + "第二段。" + "乙" * 80
    chunks = split_text(text, max_chars=90, overlap=10)
    assert len(chunks) >= 2
    assert all(chunk and len(chunk) <= 90 for chunk in chunks)


def test_code_split_keeps_line_locations() -> None:
    text = "\n".join(f"value_{index} = {index}" for index in range(100))
    chunks = split_code_lines(text, max_chars=500, overlap_lines=2)
    assert len(chunks) >= 2
    assert chunks[0][0] == 1
    assert chunks[-1][1] == 100
    assert all(start <= end and body for start, end, body in chunks)


def test_pdf_cleaning_removes_boilerplate_and_keyword_quote_artifacts() -> None:
    cleaned = clean_pdf_page_text(
        "教材官方网站：http://dblab.xmu.edu.cn\n表2-1 所有关键字\n'await  'in  while",
        set(),
    )
    assert "教材官方网站" not in cleaned
    assert "await  in  while" in cleaned


def test_section_title_is_extracted_from_numbered_heading() -> None:
    assert infer_section_title("2.3.1 Python中的变量\n正文") == "2.3.1 Python中的变量"
