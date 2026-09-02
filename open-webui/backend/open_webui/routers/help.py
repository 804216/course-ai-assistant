"""
系统帮助文档 API 路由
======================
提供文档列表和文档内容读取接口，文档源为项目根目录的 Markdown 文件。

目前支持的文档 ID：
  - project-guide：读取 `<项目根>/项目说明.md`
"""
from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from open_webui.utils.auth import get_verified_user

log = logging.getLogger(__name__)

router = APIRouter()


# ------------------------------------------------------------
# 路径定位：向上回溯到 open-webui 项目根目录
# routers/help.py → open_webui/ → backend/ → open-webui/
# ------------------------------------------------------------
_ROUTERS_DIR = Path(__file__).resolve().parent  # routers/
_BACKEND_DIR = _ROUTERS_DIR.parent.parent  # backend/（routers 是 open_webui.routers，实际是 open_webui 下）
# 真实层级： routers/ → open_webui/ → backend/ → open-webui/
_PROJECT_ROOT: Path = _ROUTERS_DIR.parent.parent.parent
_DOC_PATH_OVERRIDE: Path | None = None  # 测试时可注入

# 注册的文档清单：doc_id -> 文件相对路径 / 元数据
# 后续要扩展文档，只需在此处追加条目
_REGISTERED_DOCS: dict[str, dict[str, Any]] = {
    "project-guide": {
        "filename": "项目说明.md",
        "title": "项目说明文档",
        "description": "平台功能概述、技术栈、目录结构、开发规范与部署说明",
    }
}


# ------------------------------------------------------------
# Pydantic 响应模型
# ------------------------------------------------------------
class HelpDocSummary(BaseModel):
    id: str
    title: str
    description: str
    updated_at: int


class HelpDocDetail(HelpDocSummary):
    content: str


class HelpDocListResponse(BaseModel):
    docs: list[HelpDocSummary]


# ------------------------------------------------------------
# 工具函数
# ------------------------------------------------------------
def _resolve_doc_path(doc_id: str) -> Path | None:
    """根据 doc_id 解析出实际的 Markdown 文件路径"""
    meta = _REGISTERED_DOCS.get(doc_id)
    if not meta:
        return None
    # 允许单测注入 override 路径
    if _DOC_PATH_OVERRIDE is not None:
        return _DOC_PATH_OVERRIDE / meta["filename"]
    return _PROJECT_ROOT / meta["filename"]


def _extract_title_from_md(content: str, fallback: str) -> str:
    """从 Markdown 正文提取第一个 H1 标题作为标题"""
    m = re.search(r"^#\s+(.+)$", content, flags=re.MULTILINE)
    if m:
        return m.group(1).strip()
    return fallback


# ------------------------------------------------------------
# 路由
# ------------------------------------------------------------
@router.get("/docs", response_model=HelpDocListResponse)
async def list_help_docs(user=Depends(get_verified_user)) -> HelpDocListResponse:
    """
    返回所有已注册帮助文档的元数据列表（不含正文）。
    所有登录用户均可访问。
    """
    docs: list[HelpDocSummary] = []
    for doc_id, meta in _REGISTERED_DOCS.items():
        path = _resolve_doc_path(doc_id)
        updated_at = 0
        if path and path.exists():
            try:
                updated_at = int(path.stat().st_mtime)
            except OSError:
                updated_at = 0
        docs.append(
            HelpDocSummary(
                id=doc_id,
                title=meta["title"],
                description=meta["description"],
                updated_at=updated_at,
            )
        )
    return HelpDocListResponse(docs=docs)


@router.get("/docs/{doc_id}", response_model=HelpDocDetail)
async def get_help_doc(doc_id: str, user=Depends(get_verified_user)) -> HelpDocDetail:
    """
    根据 doc_id 返回单篇帮助文档的完整内容（Markdown 原文 + 元数据）。

    - doc_id=project-guide → 返回 `项目说明.md` 内容
    - 若 doc_id 未注册 → 404
    - 若注册了但文件物理不存在 → 500 并附带明确错误信息
    """
    meta = _REGISTERED_DOCS.get(doc_id)
    if not meta:
        raise HTTPException(status_code=404, detail=f"未知的文档 ID: {doc_id}")

    path = _resolve_doc_path(doc_id)
    if path is None or not path.exists():
        log.error(f"帮助文档文件不存在: {path}")
        raise HTTPException(
            status_code=500,
            detail=f"文档 {doc_id} 已注册但源文件缺失，请联系管理员检查部署",
        )

    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # 极端情况：非 UTF-8 编码，用 gbk 兜底（Windows 常见）
        try:
            raw = path.read_text(encoding="gbk")
        except Exception as e:
            log.error(f"读取帮助文档编码错误 {path}: {e}")
            raise HTTPException(status_code=500, detail="文档编码无法识别，请转存为 UTF-8")
    except OSError as e:
        log.error(f"读取帮助文档失败 {path}: {e}")
        raise HTTPException(status_code=500, detail=f"读取文档失败: {e}")

    try:
        updated_at = int(path.stat().st_mtime)
    except OSError:
        updated_at = int(time.time())

    # 若正文首个 H1 能覆盖配置中的默认标题，优先使用正文标题
    title = _extract_title_from_md(raw, meta["title"])
    return HelpDocDetail(
        id=doc_id,
        title=title,
        description=meta["description"],
        updated_at=updated_at,
        content=raw,
    )
