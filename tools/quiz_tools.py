"""随机抽题 + 客观题自动判分工具（Open WebUI Workspace Tool）

依赖：同目录下的 question_bank.json 作为结构化题库。
在 Open WebUI 工作空间 -> 工具 中新建工具，粘贴本文件内容；工具名可填 quiz。
部署机上的题库路径默认为仓库 tools/question_bank.json，可在 Valves 中调整。
"""

import json
import os
import random
from pydantic import BaseModel, Field


class Tools:
    class Valves(BaseModel):
        bank_path: str = Field(
            default=r"E:\ai_assistant\course-ai-assistant\tools\question_bank.json",
            description="结构化题库 JSON 文件路径",
        )

    def __init__(self):
        self.valves = self.Valves()

    def random_questions(self, chapter: str = "全部", count: int = 3, include_answer: bool = False) -> str:
        """从结构化题库中随机抽取题目（默认不返回答案）。

        Args:
            chapter: 章节号或章节名，例如“第03章”、“第5章”、“函数”；传“全部”表示所有章节。
            count: 抽取题目数量。
            include_answer: 是否在结果中包含答案与解析（教师出卷场景可用）。

        Returns:
            JSON 字符串：题目列表及其 id/类型/难度/题目/选项。
        """
        items = self._load_bank()
        if not items:
            return json.dumps({"error": "题库为空或路径有误"}, ensure_ascii=False)
        selected = self._filter_chapter(items, chapter)
        if not selected:
            return json.dumps({"error": f"未找到章节：{chapter}，可用章节见 list_bank_chapters。"}, ensure_ascii=False)
        sample = random.sample(selected, min(int(count), len(selected)))
        out = []
        for q in sample:
            entry = {
                "id": q["id"],
                "chapter": q["chapter"],
                "type": q["type"],
                "difficulty": q.get("difficulty", "easy"),
                "question": q["question"],
                "options": q.get("options", []),
            }
            if include_answer:
                entry["answer"] = q["answer"]
                entry["explanation"] = q.get("explanation", "")
            out.append(entry)
        return json.dumps({"count": len(out), "questions": out}, ensure_ascii=False, indent=2)

    def grade_objective(self, answers: str) -> str:
        """批量判分客观题（单选/判断）。

        Args:
            answers: JSON 字符串，键为题目的 id，值为学生答案，
                    例如 {"q03-01": "B", "q05-02": "正确"}。

        Returns:
            JSON 字符串：总分、总题数、正确率及每题的判定与正确答案。
        """
        try:
            stu = json.loads(answers)
        except Exception as e:
            return json.dumps({"error": f"答案格式应为 JSON，例如 {{...}}；解析失败：{e}"}, ensure_ascii=False)
        bank = self._load_bank()
        bank_by_id = {q["id"]: q for q in bank}
        detail = []
        score = 0
        total = 0
        for qid, student_answer in stu.items():
            q = bank_by_id.get(qid)
            if not q:
                detail.append({"id": qid, "status": "unknown", "note": "题库中不存在该题"})
                continue
            correct = str(student_answer).strip().lower() == str(q["answer"]).strip().lower()
            total += 1
            if correct:
                score += 1
            detail.append({
                "id": qid,
                "question": q["question"],
                "student_answer": student_answer,
                "correct_answer": q["answer"],
                "correct": correct,
                "explanation": q.get("explanation", ""),
            })
        accuracy = round(score / total * 100, 1) if total else 0
        return json.dumps({"score": score, "total": total, "accuracy": accuracy, "detail": detail},
                          ensure_ascii=False, indent=2)

    def list_bank_chapters(self) -> str:
        """列出题库中已有的章节与题量。"""
        items = self._load_bank()
        if not items:
            return json.dumps({"error": "题库为空或路径有误"}, ensure_ascii=False)
        chapters = {}
        for q in items:
            chapters[q["chapter"]] = chapters.get(q["chapter"], 0) + 1
        return json.dumps({"chapters": chapters, "total_questions": len(items)}, ensure_ascii=False, indent=2)

    def _load_bank(self) -> list:
        path = self.valves.bank_path
        if not os.path.isfile(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("chapters", [])
        except Exception:
            return []

    @staticmethod
    def _filter_chapter(items: list, chapter: str) -> list:
        text = str(chapter).strip()
        if not text or text == "全部":
            return list(items)
        import re
        num = re.search(r"(\d+)", text)
        if num:
            wanted = int(num.group(1))
            matched = []
            for q in items:
                m = re.search(r"第(\d+)章", q["chapter"])
                if m and int(m.group(1)) == wanted:
                    matched.append(q)
            if matched:
                return matched
        return [q for q in items if text in q["chapter"] or text in q.get("question", "")]
