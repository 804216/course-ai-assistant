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
- 安装：在 Open WebUI 工作空间 → 工具中新建工具，粘贴 `chapter_query_tool.py` 内容；默认数据路径为 `E:\ai_assistant\course-ai-assistant\knowledge-base`，可在工具“Valves”设置里修改。
- 启用：在“Python程序设计基础 AI 助教”模型设置中启用该工具。
