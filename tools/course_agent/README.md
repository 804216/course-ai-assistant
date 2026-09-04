# Python课程 AI 助教

项目同时保留原生代理版和 LangGraph 版。LangGraph 版通过 Open WebUI Pipe 暴露为可选模型，不另建端口或复制模型密钥：

```text
Open WebUI 前端
  -> Python课程LangGraph Pipe
     -> 输入校验与意图分类
     -> 条件分支
        -> 核心Chroma向量检索 + BM25检索 + 加权RRF融合
        -> 章节目录查询
        -> 随机练习抽取
        -> 学生答案分析
        -> 超纲/异常处理
     -> 引用校验
  -> 复用Open WebUI中的deepseek-v4-flash
```

## 工具能力

- `get_course_outline`：读取当前活动知识库的章节目录和资料统计；
- `get_chapter_materials`：按章节和资料类型查询实际文件及知识块数量；
- `sample_chapter_exercises`：从核心库的题目集合抽取指定章节练习材料，不读取答案库。

工具和 LangGraph 只读取 `DATA_DIR/course_kb`，并检查活动构建目录仍位于 `DATA_DIR` 内。参考答案集合不进入学生问答、检索或抽题路径。

## LangGraph 节点

- `normalize_input`：校验空输入、超长输入和非法章节；
- `classify_intent`：识别知识问答、概念解释、章节查询、练习生成、答案分析和超纲问题；
- `retrieve_knowledge`：在活动核心 Chroma collection 上同时执行向量检索与 BM25 检索，并通过加权 RRF 合并排名；完整清单问题继续保留精确短语优先保护；
- `chapter_tool` / `practice_tool`：执行确定性的目录查询和抽题；
- `citation_guard`：删除无效引用标签并追加真实文件来源；
- `finish`：向 Open WebUI 发送完成状态。

图实现位于 `open-webui/backend/course_agent_langgraph`，Pipe 源码为 `tools/course_agent/langgraph_pipe.py`。模型 ID 为 `python_course_langgraph`。现有 `python-course-ai-optimized` 保留作为回滚和效果对照。

Pipe 的 `BM25_WEIGHT` 默认值为 `0.3`：`0` 表示只使用向量排名，`1` 表示只使用 BM25 排名，中间值表示两者在 RRF 中的权重。默认候选池为 `max(TOP_K × 4, 20)`，最大不超过 48 个知识块。BM25 索引会按当前构建版本和过滤条件缓存；流程、比较类问题会补充同一源文件的相邻知识块。

## 验证

静态集成检查：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\validate-course-kb-windows.ps1
```

实际调用基础模型的端到端工具测试：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\smoke-test-course-agent-windows.ps1
```

LangGraph 章节工具与核心 RAG 端到端测试：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\smoke-test-course-agent-langgraph-windows.ps1
```
