# Python课程知识库构建器

该目录实现独立、版本化的课程知识库，不覆盖 Open WebUI 原有的 `webui.db`、上传文件或向量集合。

## 数据组织

- 仅解析并向量化 `.pdf`、`.py`。
- `.pyc`、字体、图片、HTML、TXT 等只写入资产清单，不进入向量库。
- 讲义、大纲、习题题目和示例代码写入核心集合。
- 习题答案写入独立答案集合，默认不绑定到普通课程助教。
- 每个块都记录章节、资料类型、文件路径以及 PDF 页码或代码行号。

运行数据默认保存在：

```text
open-webui/local-deploy/data/course_kb/
├─ active.json
└─ builds/<build-id>/
   ├─ catalog.sqlite3
   ├─ manifest.json
   └─ vector_db/
```

每次构建创建一个新版本，只有全部文件解析成功、两个 Chroma 集合数量校验通过后，才更新 `active.json`。

## 构建

功能分支已经包含可直接使用的 `20260904-v3`、`active.json` 和与该向量库匹配的本地嵌入模型。使用 Git LFS 完整克隆后，普通部署不需要执行本节的构建命令。

只有源讲义或示例代码发生变化时才需要重新构建。重新构建必须复用项目的 `open-webui/.venv` 和 `local-deploy/data/cache` 模型缓存。Windows 下使用：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-course-kb-windows.ps1
```

可通过 `-Source` 指向其他同结构资料目录。默认读取仓库中已经按章节整理的 `knowledge-base/`。

## 集成到 Open WebUI

首次克隆部署或重新构建后，启动 Open WebUI 并运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\integrate-course-kb-windows.ps1
```

脚本通过本机 Open WebUI API 幂等创建：

- `Python课程知识库（优化版）`：大纲、讲义、题目和示例代码；
- `Python课程参考答案（受控）`：答案独立保存，不默认绑定；
- `Python程序设计基础 AI 助教（优化版）`：在前端模型选择器中可选，仅绑定核心知识库。

原有知识库、原有助教和普通模型均不会被覆盖。

注意：模型权重使用 Git LFS 保存。克隆后应确认以下命令没有显示缺失对象：

```powershell
git lfs pull
git lfs ls-files
```

完成后可运行只读验证，检查目录数据库、两个向量集合、按章检索、前端模型列表和旧数据保留情况：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\validate-course-kb-windows.ps1
```
