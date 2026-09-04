# 课程专属 AI 助教（基于 Open WebUI）

小组项目仓库。项目要求详见 [docs/题目要求.md](docs/题目要求.md)，团队协作方式见 [docs/协作与部署说明.md](docs/协作与部署说明.md)，部署信息见 [docs/部署与版本说明.md](docs/部署与版本说明.md)。

## 仓库结构

```text
course-ai-assistant/
├─ README.md                 # 项目入口说明
├─ docs/                     # 题目要求、系统提示词、部署与协作说明
├─ knowledge-base/           # 整理后的课程资料（按第01–15章归档）与资料清单
├─ tools/                    # 自定义扩展工具源码
├─ config/                   # 启动脚本、环境变量示例等
├─ tests/                    # 测试问题与测试记录
├─ records/                  # 与 Codex 的交互记录、搭建记录等
└─ open-webui/               # Open WebUI v0.11.0 源码快照（不含运行时数据）
```

## 现状（2026-09-03 更新）

- 选定课程：林子雨《Python程序设计基础教程（微课版）》，覆盖第 1–15 章。
- 部署：Open WebUI v0.11.0，本机本地运行，默认地址 `http://localhost:8080`。
- 对话模型：DeepSeek（OpenAI 兼容方式接入，模型名 `deepseek-v4-flash`）。API Key 仅在本机 Open WebUI 管理界面配置，**不提交仓库**。
- RAG：本地嵌入模型 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`，向量库 Chroma。
- 知识库：Open WebUI 工作区中创建“Python程序设计”，已入库 169 个文件（讲义 PDF、习题题目/答案 PDF、教学大纲 PDF、示例代码等），约 1.5 万条向量；资料与归档状态见 [knowledge-base/资料清单.md](knowledge-base/资料清单.md)。
- 专属模型：已创建“Python程序设计基础 AI 助教”，绑定上述知识库、关闭联网搜索；系统提示词见 [docs/系统提示词.md](docs/系统提示词.md)。
- 搭建过程记录：见 [records/2026-09-03-知识库与助教搭建记录.md](records/2026-09-03-知识库与助教搭建记录.md)。

## 待填写信息

- 团队成员（4 人分工）：待填写
- 共享访问地址：`http://<部署机IP>:8080`（待部署开放后填写）
- GitHub 仓库链接：待上传后填写

## 一句话协作模式

- **代码与文件**：通过本 Git 仓库同步，成员各自改分支，完成后合并到 `main`。
- **Open WebUI 配置**（知识库、AI 助教等）：直接在共享部署机上操作，全组通过同一网址访问。
- **生效链路**：个人本地测试 -> 推送 Git -> 部署机拉取并重启 -> 全组访问共享地址验收。
- **运行时数据不入库**：`open-webui/local-deploy/`（密钥、webui.db、向量库、上传文件）仅存在于部署机，换机后通过重新上传 `knowledge-base/` 重建 RAG。

## 当前进度

- [x] M0 对齐：确定课程（Python 程序设计）、模型（DeepSeek）与知识库方向（4 人分工待补）
- [x] M1 部署与仓库：Open WebUI v0.11.0 本地运行，仓库协作结构就绪
- [x] M2 知识库：资料转换、按章归档、上传入库完成，RAG 检索链路验证通过
- [x] M3 AI 助教：专属模型“Python程序设计基础 AI 助教”已创建并绑定知识库（自定义扩展待后续补充）
- [ ] M4 测试与优化：15+ 测试题与优化前后对比待做（见 `tests/README.md`）
- [ ] M5 提交物整理：搭建记录已有，总结报告待写

## 提交安全说明

- 不提交任何 API Key、密码、`webui_secret_key.txt`、`webui.db`、向量库与上传文件。
- 需要展示或复现时：提交 `knowledge-base/` 原始资料与 docs 配置说明，在 Open WebUI 中重新上传即可重建 RAG。
