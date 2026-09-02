#!/usr/bin/env python3
"""
feature-development-workflow Skill 创建脚本
==============================
用法：
  1. 确保 open-webui 后端服务正在运行（默认 http://localhost:8080）
  2. 执行：
       python scripts/create_skill.py [--base-url http://localhost:8080] [--email admin@example.com] [--password xxx]
     如果未传 --email/--password，会提示交互输入。

功能：
  - 读取 skills/feature-development-workflow.md，解析 frontmatter + 正文
  - 登录获取 token
  - 若 Skill ID 不存在则创建，存在则更新（幂等）
  - 运行结束后输出结果
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import sys
import time
from pathlib import Path

import requests


# ------------------------------------------------------------
# 常量与路径
# ------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SKILL_MD_PATH = PROJECT_ROOT / "skills" / "feature-development-workflow.md"

SKILL_ID = "feature-development-workflow"
DEFAULT_BASE_URL = "http://localhost:8080"


# ------------------------------------------------------------
# Markdown Frontmatter 解析（不引入新依赖，手写简单解析器）
# 支持 key: value 以及 YAML 嵌套（仅处理 meta.tags 单层数组）
# ------------------------------------------------------------
def parse_frontmatter(md_text: str) -> tuple[dict, str]:
    """返回 (frontmatter_dict, body_content)"""
    if not md_text.startswith("---"):
        return {}, md_text

    m = re.match(r"^---\n(.*?)\n---\n?(.*)", md_text, re.DOTALL)
    if not m:
        return {}, md_text

    fm_text = m.group(1)
    body = m.group(2)
    fm: dict = {}
    current_key = None  # 用于处理嵌套

    lines = fm_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.strip().startswith("#"):
            i += 1
            continue

        if line.startswith(" ") or line.startswith("\t"):
            # 子项：追加到 current_key
            stripped = line.strip()
            if current_key and stripped.startswith("- "):
                value = stripped[2:].strip().strip("'\"")
                if isinstance(fm.get(current_key), list):
                    fm[current_key].append(value)
                elif isinstance(fm.get(current_key), dict):
                    # 处理 meta.tags 这种嵌套
                    nested = fm[current_key]
                    last_key = next(reversed(nested)) if nested else None
                    if last_key and isinstance(nested[last_key], list):
                        nested[last_key].append(value)
            i += 1
            continue

        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if value == "":
                # 嵌套父级或列表
                fm[key] = {}
                current_key = key
                # 检查下一行是否是数组
                j = i + 1
                while j < len(lines) and (
                    lines[j].startswith(" ") or lines[j].startswith("\t")
                ):
                    item = lines[j].strip()
                    if item.startswith("- "):
                        fm[key] = []
                        break
                    j += 1
            else:
                # 去掉引号
                value = value.strip("'\"")
                fm[key] = value
                current_key = None
        i += 1

    return fm, body


# ------------------------------------------------------------
# API 封装
# ------------------------------------------------------------
class SkillClient:
    def __init__(self, base_url: str, token: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.session = requests.Session()

    # ---- Auth ----
    def login(self, email: str, password: str) -> str:
        resp = self.session.post(
            f"{self.base_url}/api/v1/auths/signin",
            json={"email": email, "password": password},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        self.token = data["token"]
        return self.token

    def _headers(self) -> dict:
        if not self.token:
            raise RuntimeError("未登录，请先调用 login()")
        return {"Authorization": f"Bearer {self.token}"}

    # ---- Skill CRUD ----
    def get_skill_list(self) -> list[dict]:
        resp = self.session.get(
            f"{self.base_url}/api/v1/skills/", headers=self._headers(), timeout=15
        )
        resp.raise_for_status()
        return resp.json()

    def get_skill_by_id(self, skill_id: str) -> dict | None:
        """列表接口返回完整字段，可直接用。若有单条详情接口更优，但列表足够。"""
        items = self.get_skill_list()
        for item in items:
            if item.get("id") == skill_id:
                return item
        return None

    def create_skill(self, skill_id: str, name: str, description: str, content: str, meta: dict | None = None) -> dict:
        payload = {
            "id": skill_id,
            "name": name,
            "description": description,
            "content": content,
        }
        if meta is not None:
            payload["meta"] = meta
        resp = self.session.post(
            f"{self.base_url}/api/v1/skills/create",
            headers={**self._headers(), "Content-Type": "application/json"},
            json=payload,
            timeout=15,
        )
        if resp.status_code >= 400:
            print(f"[创建失败] HTTP {resp.status_code}: {resp.text[:500]}")
            resp.raise_for_status()
        return resp.json()

    def update_skill(self, skill_id: str, name: str, description: str, content: str, meta: dict | None = None) -> dict:
        payload = {
            "name": name,
            "description": description,
            "content": content,
        }
        if meta is not None:
            payload["meta"] = meta
        resp = self.session.post(
            f"{self.base_url}/api/v1/skills/{skill_id}/update",
            headers={**self._headers(), "Content-Type": "application/json"},
            json=payload,
            timeout=15,
        )
        if resp.status_code >= 400:
            print(f"[更新失败] HTTP {resp.status_code}: {resp.text[:500]}")
            resp.raise_for_status()
        return resp.json()


# ------------------------------------------------------------
# 主流程
# ------------------------------------------------------------
def wait_for_service(base_url: str, timeout_s: int = 30) -> bool:
    print(f"等待服务可用: {base_url} ...", end="", flush=True)
    start = time.time()
    while time.time() - start < timeout_s:
        try:
            r = requests.get(f"{base_url}/api/v1/configs/webui", timeout=3)
            if r.status_code < 500:
                print(" OK")
                return True
        except Exception:
            pass
        print(".", end="", flush=True)
        time.sleep(1)
    print(" 超时")
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="创建/更新 feature-development-workflow Skill")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"后端地址，默认 {DEFAULT_BASE_URL}")
    parser.add_argument("--email", help="管理员邮箱（不传则交互输入）")
    parser.add_argument("--password", help="管理员密码（不传则交互输入）")
    args = parser.parse_args()

    # 1. 检查 Skill Markdown 文件
    if not SKILL_MD_PATH.exists():
        print(f"[错误] Skill 文件不存在: {SKILL_MD_PATH}")
        return 1
    md_text = SKILL_MD_PATH.read_text(encoding="utf-8")
    frontmatter, body = parse_frontmatter(md_text)
    skill_name = frontmatter.get("name") or "功能开发标准工作流"
    skill_desc = frontmatter.get("description") or "(未填写描述)"
    skill_meta = frontmatter.get("meta")  # 可能是 dict 或 None
    print(f"[√] 读取 Skill 源文件: {SKILL_MD_PATH}")
    print(f"    ID   : {SKILL_ID}")
    print(f"    名称 : {skill_name}")
    print(f"    描述 : {skill_desc[:80]}{'...' if len(skill_desc) > 80 else ''}")
    print(f"    正文 : {len(body)} 字符")

    # 2. 等待服务可用
    if not wait_for_service(args.base_url):
        print("[错误] 后端服务不可用，请先启动 open-webui")
        return 2

    # 3. 获取凭证
    email = args.email or input("管理员邮箱: ").strip()
    password = args.password or getpass.getpass("管理员密码: ")
    if not email or not password:
        print("[错误] 邮箱和密码不能为空")
        return 3

    client = SkillClient(args.base_url)
    try:
        client.login(email, password)
        print("[√] 登录成功")
    except Exception as e:
        print(f"[错误] 登录失败: {e}")
        return 4

    # 4. 幂等操作：存在则更新，不存在则创建
    existing = client.get_skill_by_id(SKILL_ID)
    try:
        if existing:
            result = client.update_skill(SKILL_ID, skill_name, skill_desc, body, skill_meta)
            op = "更新"
        else:
            result = client.create_skill(SKILL_ID, skill_name, skill_desc, body, skill_meta)
            op = "创建"
    except Exception as e:
        print(f"[错误] Skill {op}失败: {e}")
        return 5

    print(f"[√] Skill {op}成功!")
    print(f"    记录 ID : {result.get('id')}")
    print(f"    入库名称 : {result.get('name')}")
    print(f"    创建时间 : {result.get('created_at')}")
    print(f"    更新时间 : {result.get('updated_at')}")
    print("\n你现在可以在 Workspace → Skills 中看到该 Skill，并在对话中选择使用。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
