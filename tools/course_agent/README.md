# Python课程 AI 助教

项目同时保留原生代理版和 LangGraph 版。LangGraph 版通过 Open WebUI Pipe 暴露为可选模型，不另建端口或复制模型密钥：

```text
Open WebUI 前端
  -> Python课程LangGraph Pipe
     -> 输入校验与意图分类
     -> 条件分支
        -> 核心Chroma向量检索 + BM25检索 + 加权RRF融合
        -> BAAI/bge-reranker-v2-m3 重排序 + 相邻知识块分组
        -> 证据充分性检查；不足时扩展查询并最多重试一次
        -> 章节目录查询
        -> 随机练习抽取
        -> 学生答案分析
        -> 超纲/异常处理
     -> 回答依据检查；缺少有效行内引用时最多修订一次
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
- `academic_integrity_response`：在检索和回答生成前拦截整份作业、整套习题或可直接提交报告的代做请求，并引导学生提交单题尝试；
- `retrieve_knowledge`：在活动核心 Chroma collection 上同时执行向量检索与 BM25 检索，通过加权 RRF 合并候选，再用 `BAAI/bge-reranker-v2-m3` 重排序；完整清单问题继续保留精确短语优先保护；
- `assess_evidence` / `expand_query`：结合重排分数和查询词覆盖率判断证据是否充分；不足时放宽推断过滤、扩展教材检索词并最多重试一次；
- `chapter_tool` / `practice_tool`：执行确定性的目录查询和抽题；
- `grounding_guard` / `revise_answer`：要求知识回答至少包含一个有效的 `[资料N]` 行内引用；不满足时依据原证据修订一次；
- `citation_guard`：删除无效引用标签并追加真实文件来源；
- `finish`：向 Open WebUI 发送完成状态。

图实现位于 `open-webui/backend/course_agent_langgraph`，Pipe 源码为 `tools/course_agent/langgraph_pipe.py`。模型 ID 为 `python_course_langgraph`。现有 `python-course-ai-optimized` 保留作为回滚和效果对照。

Pipe 的 `BM25_WEIGHT` 默认值为 `0.3`：`0` 表示只使用向量排名，`1` 表示只使用 BM25 排名，中间值表示两者在 RRF 中的权重。默认从融合排名中取最多 40 个候选交给重排模型，再从重排后的 12 个候选中按问题类型动态选择 3 至 8 个证据组。相邻知识块会合并成一个证据组，避免占满最终名额，同时保留连续讲义上下文。重排服务不可用时会自动降级到 RRF 顺序。

Pipe 1.5.0 在初始化时只编译一次 LangGraph，每次请求通过 LangGraph Runtime Context 注入用户、模型、数据目录和阀门参数。课程系统规则始终作为不可覆盖策略加载，界面附加的 system 消息只能补充回答风格。默认 `EVIDENCE_MIN_SCORE=0.05`、`EVIDENCE_MIN_COVERAGE=0.08`，可通过 Pipe 阀门按评测集结果调整。

1.5.0 增加零基础、初学者、进阶学习者和备考复习四档教学策略；代码证据会保留真实行号范围；练习生成采用“章节—知识点—难度—题目—作答要求—提示”，答案点评采用“正确之处—存在问题—改进建议—自我检查”。完整验收结论见 `docs/课程知识库与AI助教验收说明.md`。

本机启动脚本会读取 `open-webui/.env.example` 中的 `rerank-key`，只在子进程内设置 `COURSE_RERANK_API_KEY`，不会写入 Open WebUI 数据库或日志。默认接口为 `https://api.siliconflow.cn/v1/rerank`，模型为 `BAAI/bge-reranker-v2-m3`。包含真实密钥的 `.env.example` 不应提交到 Git；正式部署建议改用系统环境变量 `COURSE_RERANK_API_KEY`。

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
