"""章节查询工具（Open WebUI Workspace Tool）

用法：在 Open WebUI 的 工作空间 -> 工具 中新建工具，把本文件内容整体粘贴进去，
工具名为 chapter_query。然后在“Python程序设计基础 AI 助教”模型设置中启用该工具。

功能：输入章节，返回该章目录下“讲义/题目/答案 PDF”与“示例代码”文件清单。
数据来自本机仓库的 knowledge-base，是真实的结构化目录数据。
"""

import json
import os
import re
from pydantic import BaseModel, Field


class Tools:
    class Valves(BaseModel):
        # 部署机上知识库归档目录（仓库里的 knowledge-base），可自行调整
        base_path: str = Field(
            default=r"E:\ai_assistant\course-ai-assistant\knowledge-base",
            description="知识库归档根目录",
        )

    def __init__(self):
        self.valves = self.Valves()

    def list_chapters(self) -> str:
        """列出课程全部章节编号与名称，供学生/助教查询各章资料时使用。"""
        root = self.valves.base_path
        if not os.path.isdir(root):
            return json.dumps(
                {"error": f"知识库目录不存在: {root}"}, ensure_ascii=False
            )
        dirs = [
            d
            for d in sorted(os.listdir(root))
            if os.path.isdir(os.path.join(root, d)) and d.startswith("第")
        ]
        chapters = []
        for d in dirs:
            chapters.append(
                {
                    "chapter_id": os.path.basename(d),
                    "chapter_dir": d,
                    "title": d,
                }
            )
        return json.dumps({"chapters": chapters, "total": len(chapters)}, ensure_ascii=False)

    def query_chapter(self, chapter: str) -> str:
        """查询指定章节的资料清单。

        Args:
            chapter: 章节号或章节名，例如“第7章”、“7”、“面向对象程序设计”。

        Returns:
            JSON 字符串，包含该章目录、讲义/题目/答案 PDF 与示例代码文件列表。
        """
        root = self.valves.base_path
        if not os.path.isdir(root):
            return json.dumps(
                {"error": f"知识库目录不存在: {root}"}, ensure_ascii=False
            )
        dirs = [
            d
            for d in sorted(os.listdir(root))
            if os.path.isdir(os.path.join(root, d)) and d.startswith("第")
        ]
        target = self._match_chapter(chapter, dirs)
        if target is None:
            return json.dumps(
                {"error": f"未找到章节：{chapter}，可用章节见 list_chapters。"},
                ensure_ascii=False,
            )

        chapter_root = os.path.join(root, target)
        pdfs = []
        code = []
        for name in sorted(os.listdir(chapter_root)):
            full = os.path.join(chapter_root, name)
            if os.path.isfile(full) and name.lower().endswith(".pdf"):
                pdfs.append(
                    {
                        "file": name,
                        "type": self._pdf_type(name),
                        "path": os.path.relpath(full, root),
                    }
                )
        code_dir = os.path.join(chapter_root, "示例代码")
        if os.path.isdir(code_dir):
            for name in sorted(os.listdir(code_dir)):
                code.append(
                    {
                        "file": name,
                        "type": "示例代码",
                        "path": os.path.relpath(os.path.join(code_dir, name), root),
                    }
                )
        return json.dumps(
            {
                "chapter_id": target,
                "title": target,
                "materials": pdfs,
                "example_code": code,
                "total_files": len(pdfs) + len(code),
            },
            ensure_ascii=False,
            indent=2,
        )

    @staticmethod
    def _pdf_type(name: str) -> str:
        if "讲义" in name:
            return "讲义"
        if "题目" in name:
            return "题目"
        if "答案" in name:
            return "答案"
        return "其他PDF"

    @staticmethod
    def _match_chapter(chapter: str, dirs: list) -> str | None:
        text = str(chapter).strip()
        num = re.search(r"(\d+)", text)
        if num:
            wanted = int(num.group(1))
            for d in dirs:
                m = re.search(r"第(\d+)章", d)
                if m and int(m.group(1)) == wanted:
                    return d
        for d in dirs:
            if text in d or d in text:
                return d
        return None
