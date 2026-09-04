from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import os
import re
import sqlite3
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

COURSE_NAME = "Python程序设计基础教程（微课版）"
DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
CHAPTER_TITLES = {
    0: "课程说明",
    1: "Python语言概述",
    2: "基础语法知识",
    3: "程序控制结构",
    4: "序列",
    5: "字符串",
    6: "函数",
    7: "面向对象程序设计",
    8: "模块",
    9: "异常处理",
    10: "基于文件的持久化",
    11: "基于数据库的持久化",
    12: "图形用户界面编程",
    13: "正则表达式",
    14: "网络爬虫",
    15: "常用的标准库和第三方库",
}
INDEXABLE_EXTENSIONS = {".pdf", ".py"}
ASSET_SUFFIXES = (".txt", ".html", ".png", ".ico", ".csv", ".db", ".ttf")


@dataclass(slots=True)
class SourceRecord:
    id: str
    relative_path: str
    filename: str
    extension: str
    sha256: str
    size: int
    chapter_no: int
    chapter_title: str
    resource_type: str
    encoding: str | None
    parse_status: str
    issue: str | None
    details: dict[str, Any]


@dataclass(slots=True)
class ChunkRecord:
    id: str
    file_id: str
    collection_role: str
    ordinal: int
    text: str
    text_hash: str
    chapter_no: int
    chapter_title: str
    resource_type: str
    source: str
    source_path: str
    section_title: str = ""
    page_start: int | None = None
    page_end: int | None = None
    line_start: int | None = None
    line_end: int | None = None
    quality: str = "ok"

    def vector_metadata(self, build_id: str, model_name: str) -> dict[str, Any]:
        data = {
            "file_id": self.file_id,
            "source": self.source,
            "source_path": self.source_path,
            "chapter_no": self.chapter_no,
            "chapter": f"第{self.chapter_no:02d}章" if self.chapter_no else "课程说明",
            "chapter_title": self.chapter_title,
            "resource_type": self.resource_type,
            "ordinal": self.ordinal,
            "section_title": self.section_title,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "quality": self.quality,
            "text_hash": self.text_hash,
            "build_id": build_id,
            "embedding_model": model_name,
        }
        return {key: value for key, value in data.items() if value is not None}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_text(text: str) -> str:
    text = text.replace("\u00a0", " ").replace("\u200b", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chapter_from_path(relative_path: Path) -> int:
    candidates = [*relative_path.parts, relative_path.stem]
    patterns = (
        re.compile(r"第\s*0?(\d{1,2})\s*章", re.IGNORECASE),
        re.compile(r"chapter\s*0?(\d{1,2})", re.IGNORECASE),
    )
    for candidate in candidates:
        for pattern in patterns:
            match = pattern.search(candidate)
            if match:
                value = int(match.group(1))
                if 1 <= value <= 15:
                    return value
    if "教学大纲" in str(relative_path) or "课程说明" in relative_path.parts:
        return 0
    return 0


def resource_type_for(relative_path: Path) -> str:
    if relative_path.suffix.lower() == ".py":
        return "code"
    name = relative_path.name
    path_text = str(relative_path)
    if "答案" in name:
        return "exercise_answer"
    if "题目" in name:
        return "exercise_question"
    if "教学大纲" in path_text or "课程说明" in relative_path.parts:
        return "syllabus"
    return "lecture"


def document_header(record: SourceRecord, locator: str) -> str:
    chapter = "课程说明" if record.chapter_no == 0 else f"第{record.chapter_no:02d}章 {record.chapter_title}"
    type_names = {
        "syllabus": "教学大纲",
        "lecture": "课程讲义",
        "exercise_question": "教材习题题目",
        "exercise_answer": "教材习题答案",
        "code": "示例代码",
    }
    return (
        f"课程：{COURSE_NAME}\n"
        f"章节：{chapter}\n"
        f"资料类型：{type_names.get(record.resource_type, record.resource_type)}\n"
        f"来源：{record.relative_path}\n"
        f"位置：{locator}\n"
    )


def split_text(text: str, max_chars: int, overlap: int) -> list[str]:
    text = normalize_text(text)
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        if end < len(text):
            search_start = min(end, start + max_chars // 2)
            breakpoints = [
                text.rfind("\n\n", search_start, end),
                text.rfind("\n", search_start, end),
                text.rfind("。", search_start, end),
                text.rfind("；", search_start, end),
            ]
            boundary = max(breakpoints)
            if boundary > start:
                end = boundary + 1
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def repeated_pdf_lines(page_texts: list[str]) -> set[str]:
    page_count = len(page_texts)
    if page_count < 4:
        return set()
    frequency: Counter[str] = Counter()
    for text in page_texts:
        lines = {line.strip() for line in text.splitlines() if line.strip()}
        frequency.update(lines)
    threshold = max(4, math.ceil(page_count * 0.3))
    return {
        line
        for line, count in frequency.items()
        if count >= threshold and len(line) <= 100 and not re.search(r"\b(def|class|for|while|if)\b", line)
    }


_PDF_BOILERPLATE_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"教材官方网站",
        r"https?://(?:www\.)?dblab\.xmu\.edu\.cn",
        r"\bE-?mail\s*[:：]",
        r"^\s*(?:主讲教师|授课教师|教师简介|作者简介)\s*[:：]",
        r"本\s*PPT\s*是如下教材的配套讲义",
        r"^\s*Python程序设计基础教程[（(]微课版[）)]\s*$",
        r"^\s*林子雨.*(?:教授|博士|主页|邮箱)\s*$",
    )
)


def clean_pdf_page_text(text: str, repeated: set[str]) -> str:
    """Remove presentation boilerplate while preserving course statements."""
    lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line in repeated:
            continue
        if any(pattern.search(line) for pattern in _PDF_BOILERPLATE_PATTERNS):
            continue
        lines.append(raw_line)
    cleaned = normalize_text("\n".join(lines))
    # Some PPT table cells are extracted as a leading apostrophe (for example
    # ``'await`` and ``'in``); it is not part of the Python keyword.
    cleaned = re.sub(r"(?<![\w'])['‘’](?=(?:await|in)\b)", "", cleaned)
    return normalize_text(cleaned)


def infer_section_title(text: str) -> str:
    for line in text.splitlines()[:20]:
        candidate = re.sub(r"\s+", " ", line).strip(" #\t")
        if re.match(r"^\d{1,2}(?:\.\d+){1,3}\s*\S.{1,78}$", candidate):
            return candidate[:100]
        if re.match(r"^第\s*\d{1,2}\s*(?:章|节)\s*\S.{0,70}$", candidate):
            return candidate[:100]
    return ""


def is_low_value_pdf_page(page_no: int, text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return True
    if page_no <= 2 and len(compact) < 120 and any(
        marker in compact for marker in ("课程讲义", "教材", "主讲", "教师", "大学")
    ):
        return True
    return False


def make_chunk_id(source_hash: str, locator: str, text: str) -> str:
    return sha256_bytes(f"{source_hash}\0{locator}\0{text}".encode("utf-8"))


def build_pdf_chunks(path: Path, record: SourceRecord, max_chars: int, overlap: int) -> list[ChunkRecord]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    raw_pages = [normalize_text(page.extract_text() or "") for page in reader.pages]
    repeated = repeated_pdf_lines(raw_pages)
    pages: list[tuple[int, str]] = []
    skipped_low_value_pages: list[int] = []
    for page_no, text in enumerate(raw_pages, start=1):
        cleaned = clean_pdf_page_text(text, repeated)
        if is_low_value_pdf_page(page_no, cleaned):
            skipped_low_value_pages.append(page_no)
        else:
            pages.append((page_no, cleaned))

    groups: list[tuple[int, int, str]] = []
    current_pages: list[int] = []
    current_parts: list[str] = []
    current_size = 0
    target_body = max(300, max_chars - 230)

    def flush() -> None:
        nonlocal current_pages, current_parts, current_size
        if current_pages and current_parts:
            groups.append((current_pages[0], current_pages[-1], "\n\n".join(current_parts)))
        current_pages, current_parts, current_size = [], [], 0

    for page_no, text in pages:
        for piece in split_text(text, target_body, overlap):
            if current_parts and current_size + len(piece) + 2 > target_body:
                flush()
            current_pages.append(page_no)
            current_parts.append(piece)
            current_size += len(piece) + 2
    flush()

    chunks: list[ChunkRecord] = []
    for ordinal, (page_start, page_end, body) in enumerate(groups):
        locator = f"第{page_start}页" if page_start == page_end else f"第{page_start}-{page_end}页"
        text = f"{document_header(record, locator)}\n{body}"
        chunk_id = make_chunk_id(record.sha256, locator, text)
        chunks.append(
            ChunkRecord(
                id=chunk_id,
                file_id=record.id,
                collection_role="solutions" if record.resource_type == "exercise_answer" else "core",
                ordinal=ordinal,
                text=text,
                text_hash=sha256_bytes(text.encode("utf-8")),
                chapter_no=record.chapter_no,
                chapter_title=record.chapter_title,
                resource_type=record.resource_type,
                source=record.filename,
                source_path=record.relative_path,
                section_title=infer_section_title(body),
                page_start=page_start,
                page_end=page_end,
            )
        )

    record.details.update(
        {
            "page_count": len(raw_pages),
            "nonempty_page_count": len(pages),
            "skipped_low_value_pages": skipped_low_value_pages,
            "removed_repeated_lines": sorted(repeated),
        }
    )
    return chunks


def decode_python(raw: bytes) -> tuple[str, str, str | None]:
    first_two = raw.splitlines()[:2]
    declared = None
    cookie_re = re.compile(rb"coding[:=]\s*([-\w.]+)")
    for line in first_two:
        match = cookie_re.search(line)
        if match:
            declared = match.group(1).decode("ascii", errors="replace")
            break

    for encoding in ("utf-8-sig", "gb18030"):
        try:
            text = raw.decode(encoding)
            mismatch = declared if declared and declared.lower().replace("_", "-") not in encoding else None
            return text, encoding, mismatch
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8-replace", declared


def extract_code_details(text: str) -> tuple[dict[str, Any], str | None]:
    details: dict[str, Any] = {
        "imports": [],
        "definitions": [],
        "asset_references": [],
    }
    syntax_error = None
    try:
        tree = ast.parse(text)
        imports: set[str] = set()
        definitions: list[str] = []
        assets: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                definitions.append(node.name)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value.lower().endswith(ASSET_SUFFIXES):
                    assets.add(node.value)
        details.update(
            {
                "imports": sorted(imports),
                "definitions": definitions,
                "asset_references": sorted(assets),
            }
        )
    except SyntaxError as exc:
        syntax_error = f"第{exc.lineno}行：{exc.msg}"
    return details, syntax_error


def split_code_lines(text: str, max_chars: int, overlap_lines: int = 3) -> list[tuple[int, int, str]]:
    lines = text.splitlines()
    if not lines:
        return []
    result: list[tuple[int, int, str]] = []
    start = 0
    body_limit = max(300, max_chars - 420)
    while start < len(lines):
        end = start
        size = 0
        while end < len(lines) and (size + len(lines[end]) + 1 <= body_limit or end == start):
            size += len(lines[end]) + 1
            end += 1
        body = "\n".join(lines[start:end]).strip("\n")
        if body.strip():
            result.append((start + 1, end, body))
        if end >= len(lines):
            break
        start = max(start + 1, end - overlap_lines)
    return result


def build_code_chunks(path: Path, record: SourceRecord, max_chars: int) -> list[ChunkRecord]:
    raw = path.read_bytes()
    text, encoding, declared_mismatch = decode_python(raw)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    record.encoding = encoding
    details, syntax_error = extract_code_details(text)
    if declared_mismatch:
        details["declared_encoding_mismatch"] = declared_mismatch
    record.details.update(details)

    if not text.strip():
        record.parse_status = "skipped"
        record.issue = "空Python模块，仅保留包结构，不生成向量"
        return []

    quality = "syntax_error" if syntax_error else "ok"
    if syntax_error:
        record.parse_status = "warning"
        record.issue = syntax_error

    imports = "、".join(details["imports"]) or "无"
    definitions = "、".join(details["definitions"]) or "文件级示例"
    assets = "、".join(details["asset_references"]) or "无"
    warning = f"\n质量提示：源码存在语法错误（{syntax_error}），仅可作为错误分析材料。" if syntax_error else ""
    card = f"定义：{definitions}\n依赖模块：{imports}\n外部资源：{assets}{warning}"

    chunks: list[ChunkRecord] = []
    for ordinal, (line_start, line_end, body) in enumerate(split_code_lines(text, max_chars)):
        locator = f"第{line_start}-{line_end}行"
        text_value = f"{document_header(record, locator)}\n代码信息：{card}\n\n```python\n{body}\n```"
        chunk_id = make_chunk_id(record.sha256, locator, text_value)
        chunks.append(
            ChunkRecord(
                id=chunk_id,
                file_id=record.id,
                collection_role="core",
                ordinal=ordinal,
                text=text_value,
                text_hash=sha256_bytes(text_value.encode("utf-8")),
                chapter_no=record.chapter_no,
                chapter_title=record.chapter_title,
                resource_type="code",
                source=record.filename,
                source_path=record.relative_path,
                section_title=(
                    "、".join(details["definitions"][:3])
                    if details["definitions"]
                    else path.stem
                ),
                line_start=line_start,
                line_end=line_end,
                quality=quality,
            )
        )
    return chunks


def create_catalog(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.executescript("""
        PRAGMA foreign_keys=ON;
        CREATE TABLE build (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            source_root TEXT NOT NULL,
            embedding_model TEXT NOT NULL,
            embedding_dimension INTEGER,
            core_collection TEXT NOT NULL,
            solutions_collection TEXT NOT NULL,
            status TEXT NOT NULL,
            summary_json TEXT NOT NULL
        );
        CREATE TABLE source_file (
            id TEXT PRIMARY KEY,
            relative_path TEXT NOT NULL UNIQUE,
            filename TEXT NOT NULL,
            extension TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            size INTEGER NOT NULL,
            chapter_no INTEGER NOT NULL,
            chapter_title TEXT NOT NULL,
            resource_type TEXT NOT NULL,
            encoding TEXT,
            parse_status TEXT NOT NULL,
            issue TEXT,
            details_json TEXT NOT NULL
        );
        CREATE TABLE chunk (
            id TEXT PRIMARY KEY,
            file_id TEXT NOT NULL REFERENCES source_file(id),
            collection_role TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            text_hash TEXT NOT NULL,
            chapter_no INTEGER NOT NULL,
            resource_type TEXT NOT NULL,
            source TEXT NOT NULL,
            section_title TEXT NOT NULL,
            page_start INTEGER,
            page_end INTEGER,
            line_start INTEGER,
            line_end INTEGER,
            char_count INTEGER NOT NULL,
            UNIQUE(file_id, collection_role, ordinal)
        );
        CREATE INDEX ix_chunk_chapter_type ON chunk(chapter_no, resource_type);
        CREATE TABLE asset (
            id TEXT PRIMARY KEY,
            relative_path TEXT NOT NULL UNIQUE,
            extension TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            size INTEGER NOT NULL,
            chapter_no INTEGER NOT NULL
        );
        """)
    return connection


def chunked(values: list[Any], size: int) -> Iterable[list[Any]]:
    for offset in range(0, len(values), size):
        yield values[offset : offset + size]


def resolve_cached_model(project_root: Path, model_name: str) -> Path:
    repo_dir = (
        project_root
        / "open-webui"
        / "local-deploy"
        / "data"
        / "cache"
        / "huggingface"
        / "hub"
        / f"models--{model_name.replace('/', '--')}"
    )
    ref = repo_dir / "refs" / "main"
    if ref.is_file():
        snapshot = repo_dir / "snapshots" / ref.read_text(encoding="utf-8").strip()
        if (snapshot / "config.json").is_file():
            return snapshot
    snapshots = sorted((repo_dir / "snapshots").glob("*")) if (repo_dir / "snapshots").is_dir() else []
    for snapshot in reversed(snapshots):
        if (snapshot / "config.json").is_file():
            return snapshot
    raise FileNotFoundError(f"未找到本地嵌入模型缓存：{model_name}（查找目录：{repo_dir}）")


def build_index(args: argparse.Namespace) -> dict[str, Any]:
    project_root = Path(__file__).resolve().parents[2]
    source_root = Path(args.source).resolve()
    output_root = Path(args.output).resolve()
    if not source_root.is_dir():
        raise FileNotFoundError(f"知识库源目录不存在：{source_root}")

    build_id = args.build_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_build_id = re.sub(r"[^A-Za-z0-9_-]", "-", build_id).lower()
    build_dir = output_root / "builds" / safe_build_id
    if build_dir.exists():
        raise FileExistsError(f"构建目录已存在，拒绝覆盖：{build_dir}")
    vector_path = build_dir / "vector_db"
    build_dir.mkdir(parents=True)
    vector_path.mkdir()

    core_collection = f"python-course-core-{safe_build_id}"
    solutions_collection = f"python-course-solutions-{safe_build_id}"
    catalog = create_catalog(build_dir / "catalog.sqlite3")
    created_at = datetime.now(timezone.utc).isoformat()
    summary: dict[str, Any] = {
        "build_id": safe_build_id,
        "created_at": created_at,
        "source_root": str(source_root),
        "embedding_model": args.model,
        "embedding_dimension": None,
        "vector_path": (Path("builds") / safe_build_id / "vector_db").as_posix(),
        "core_collection": core_collection,
        "solutions_collection": solutions_collection,
        "source_files": 0,
        "source_status": {},
        "assets": 0,
        "core_chunks": 0,
        "solution_chunks": 0,
        "warnings": [],
        "chapters": {},
    }
    catalog.execute(
        "INSERT INTO build VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            safe_build_id,
            created_at,
            str(source_root),
            args.model,
            None,
            core_collection,
            solutions_collection,
            "building",
            json.dumps(summary, ensure_ascii=False),
        ),
    )
    catalog.commit()

    records: list[SourceRecord] = []
    chunks: list[ChunkRecord] = []
    try:
        all_files = sorted(path for path in source_root.rglob("*") if path.is_file())
        for path in all_files:
            relative = path.relative_to(source_root)
            extension = path.suffix.lower()
            raw = path.read_bytes()
            digest = sha256_bytes(raw)
            chapter_no = chapter_from_path(relative)
            chapter_title = CHAPTER_TITLES[chapter_no]
            if extension not in INDEXABLE_EXTENSIONS:
                asset_id = sha256_bytes(f"asset\0{relative.as_posix()}\0{digest}".encode("utf-8"))
                catalog.execute(
                    "INSERT INTO asset VALUES (?, ?, ?, ?, ?, ?)",
                    (asset_id, relative.as_posix(), extension, digest, len(raw), chapter_no),
                )
                summary["assets"] += 1
                continue

            record = SourceRecord(
                id=sha256_bytes(f"file\0{relative.as_posix()}\0{digest}".encode("utf-8")),
                relative_path=relative.as_posix(),
                filename=path.name,
                extension=extension,
                sha256=digest,
                size=len(raw),
                chapter_no=chapter_no,
                chapter_title=chapter_title,
                resource_type=resource_type_for(relative),
                encoding=None,
                parse_status="completed",
                issue=None,
                details={},
            )
            try:
                new_chunks = (
                    build_pdf_chunks(path, record, args.max_chars, args.overlap)
                    if extension == ".pdf"
                    else build_code_chunks(path, record, args.max_chars)
                )
                if not new_chunks and record.parse_status == "completed":
                    record.parse_status = "skipped"
                    record.issue = "未提取到可索引文本"
                chunks.extend(new_chunks)
            except Exception as exc:
                record.parse_status = "failed"
                record.issue = f"{type(exc).__name__}: {exc}"
                summary["warnings"].append(f"{record.relative_path}: {record.issue}")
            if record.parse_status == "warning" and record.issue:
                summary["warnings"].append(f"{record.relative_path}: {record.issue}")
            records.append(record)

        for record in records:
            catalog.execute(
                "INSERT INTO source_file VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.id,
                    record.relative_path,
                    record.filename,
                    record.extension,
                    record.sha256,
                    record.size,
                    record.chapter_no,
                    record.chapter_title,
                    record.resource_type,
                    record.encoding,
                    record.parse_status,
                    record.issue,
                    json.dumps(record.details, ensure_ascii=False),
                ),
            )
        for item in chunks:
            catalog.execute(
                "INSERT INTO chunk VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    item.id,
                    item.file_id,
                    item.collection_role,
                    item.ordinal,
                    item.text_hash,
                    item.chapter_no,
                    item.resource_type,
                    item.source,
                    item.section_title,
                    item.page_start,
                    item.page_end,
                    item.line_start,
                    item.line_end,
                    len(item.text),
                ),
            )
        catalog.commit()

        if not chunks:
            raise RuntimeError("没有生成任何知识块")
        failed = [record for record in records if record.parse_status == "failed"]
        if failed:
            raise RuntimeError(f"有 {len(failed)} 个源文件解析失败，构建未发布")

        model_path = (
            Path(args.model_path).resolve() if args.model_path else resolve_cached_model(project_root, args.model)
        )
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        from sentence_transformers import SentenceTransformer
        import chromadb

        model = SentenceTransformer(str(model_path), local_files_only=True)
        dimension = int(model.get_embedding_dimension())
        summary["embedding_dimension"] = dimension
        client = chromadb.PersistentClient(path=str(vector_path))

        by_role = {
            "core": [item for item in chunks if item.collection_role == "core"],
            "solutions": [item for item in chunks if item.collection_role == "solutions"],
        }
        for role, role_chunks in by_role.items():
            collection_name = core_collection if role == "core" else solutions_collection
            collection = client.get_or_create_collection(collection_name, metadata={"hnsw:space": "cosine"})
            for batch in chunked(role_chunks, args.batch_size):
                texts = [item.text.replace("\n", " ") for item in batch]
                vectors = model.encode(
                    texts,
                    batch_size=args.batch_size,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                ).tolist()
                collection.upsert(
                    ids=[item.id for item in batch],
                    documents=[item.text for item in batch],
                    embeddings=vectors,
                    metadatas=[item.vector_metadata(safe_build_id, args.model) for item in batch],
                )
            if collection.count() != len(role_chunks):
                raise RuntimeError(
                    f"集合 {collection_name} 数量不一致：expected={len(role_chunks)} actual={collection.count()}"
                )

        summary["source_files"] = len(records)
        summary["source_status"] = dict(Counter(record.parse_status for record in records))
        summary["core_chunks"] = len(by_role["core"])
        summary["solution_chunks"] = len(by_role["solutions"])
        chapter_stats: dict[str, dict[str, int]] = {}
        for chapter_no in range(0, 16):
            chapter_items = [item for item in chunks if item.chapter_no == chapter_no]
            if chapter_items:
                chapter_stats[str(chapter_no)] = {
                    "files": len({item.file_id for item in chapter_items}),
                    "core_chunks": sum(item.collection_role == "core" for item in chapter_items),
                    "solution_chunks": sum(item.collection_role == "solutions" for item in chapter_items),
                }
        summary["chapters"] = chapter_stats

        catalog.execute(
            "UPDATE build SET embedding_dimension=?, status=?, summary_json=? WHERE id=?",
            (dimension, "ready", json.dumps(summary, ensure_ascii=False), safe_build_id),
        )
        catalog.commit()
        manifest_path = build_dir / "manifest.json"
        manifest_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        output_root.mkdir(parents=True, exist_ok=True)
        active_tmp = output_root / "active.json.tmp"
        active_tmp.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(active_tmp, output_root / "active.json")
        return summary
    except Exception:
        catalog.execute(
            "UPDATE build SET status=?, summary_json=? WHERE id=?",
            ("failed", json.dumps(summary, ensure_ascii=False), safe_build_id),
        )
        catalog.commit()
        raise
    finally:
        catalog.close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="构建按章节组织的Python课程知识库")
    parser.add_argument("--source", default=str(project_root / "knowledge-base"), help="整理后的课程资料目录")
    parser.add_argument(
        "--output",
        default=str(project_root / "open-webui" / "local-deploy" / "data" / "course_kb"),
        help="版本化知识库运行目录",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--model-path", default=None, help="可选：本地SentenceTransformer模型快照")
    parser.add_argument("--max-chars", type=int, default=1000)
    parser.add_argument("--overlap", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--build-id", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = build_index(args)
    except Exception as exc:
        print(f"构建失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
