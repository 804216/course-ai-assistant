# 自定义扩展工具

要求：

- 有明确输入与输出；
- 能被 Open WebUI 对话调用；
- 建议使用 Workspace Tool、Skill 或外部 API 实现；
- 仅用提示词模拟不计入完成。

当前计划（待定）：例如随机抽题 / 客观题判分 / 学习计划生成等，确认后在此填写实现方式与调用说明。

## 已完成：章节查询工具（chapter_query）

- 文件：`tools/chapter_query_tool.py`
- 功能：输入章节号或章节名，返回该章“讲义/题目/答案 PDF”与“示例代码”清单。
- 数据来源：仓库 `knowledge-base/` 下按“第NN章-章节名”归档的真实目录。
- 实现方式：Open WebUI Workspace Tool（Python，结构化 JSON 输出）。
- 安装：运行 `scripts/integrate-course-kb-windows.ps1` 时自动注册；也可在 Open WebUI 工作空间 → 工具中手工新建并粘贴 `chapter_query_tool.py`。Valves 默认留空时会自动从运行目录向上查找仓库内的 `knowledge-base/`。
- 启用：自动集成时会绑定到“Python程序设计基础 AI 助教（优化版）”；其他模型可在设置中手工启用。

## 已完成：随机抽题 + 客观题判分工具（quiz）

- 文件：`tools/quiz_tools.py`
- 数据：`tools/question_bank.json`（结构化题库，含题目 id/章节/类型/难度/选项/答案/解析）
- 功能：
  - `random_questions(chapter, count, include_answer)`：按章节随机抽题，默认不返回答案；
  - `grade_objective(answers)`：批量判分单选题/判断题，返回得分、总分、正确率与逐题判定；
  - `list_bank_chapters()`：列出题库中已有章节与题量。
- 实现方式：Open WebUI Workspace Tool（真实读取题库 JSON、随机抽样、规则判分，非提示词模拟）。
- 安装：运行 `scripts/integrate-course-kb-windows.ps1` 时自动注册并绑定到优化版助教；也可在工作空间 → 工具中手工新建并粘贴 `quiz_tools.py`。Valves 默认留空时会自动向上查找仓库内 `tools/question_bank.json`。

