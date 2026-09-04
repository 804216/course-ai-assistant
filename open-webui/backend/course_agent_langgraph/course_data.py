from __future__ import annotations

import datetime as dt
import hashlib
import json
import random
import sqlite3
from pathlib import Path
from typing import Any

CHAPTER_TITLES = {
    0: '课程说明',
    1: 'Python语言概述',
    2: '基础语法知识',
    3: '程序控制结构',
    4: '序列',
    5: '字符串',
    6: '函数',
    7: '面向对象程序设计',
    8: '模块',
    9: '异常处理',
    10: '基于文件的持久化',
    11: '基于数据库的持久化',
    12: '图形用户界面编程',
    13: '正则表达式',
    14: '网络爬虫',
    15: '常用的标准库和第三方库',
}

RESOURCE_ALIASES = {
    'all': 'all',
    '全部': 'all',
    '所有': 'all',
    'syllabus': 'syllabus',
    '大纲': 'syllabus',
    '教学大纲': 'syllabus',
    'lecture': 'lecture',
    '讲义': 'lecture',
    '课件': 'lecture',
    'exercise_question': 'exercise_question',
    '题目': 'exercise_question',
    '习题': 'exercise_question',
    'code': 'code',
    '代码': 'code',
    '示例代码': 'code',
}


def normalize_resource_type(value: str) -> str:
    normalized = RESOURCE_ALIASES.get((value or 'all').strip().lower())
    if not normalized:
        allowed = 'all、lecture、exercise_question、code、syllabus'
        raise ValueError(f'不支持的资料类型：{value}。可选值：{allowed}')
    return normalized


class CourseData:
    """Read-only access to the active course catalog and Chroma collections."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir.resolve()

    def paths(self) -> tuple[Path, dict[str, Any]]:
        active_path = self.data_dir / 'course_kb' / 'active.json'
        if not active_path.is_file():
            raise RuntimeError(f'课程知识库尚未构建：{active_path}')
        active = json.loads(active_path.read_text(encoding='utf-8'))
        build_dir = (self.data_dir / 'course_kb' / 'builds' / active['build_id']).resolve()
        vector_path = Path(active['vector_path'])
        if not vector_path.is_absolute():
            vector_path = active_path.parent / vector_path
        vector_path = vector_path.resolve()
        try:
            build_dir.relative_to(self.data_dir)
            vector_path.relative_to(self.data_dir)
        except ValueError as exc:
            raise RuntimeError('课程知识库路径不在 DATA_DIR 内') from exc
        catalog_path = build_dir / 'catalog.sqlite3'
        if not catalog_path.is_file() or not vector_path.is_dir():
            raise RuntimeError('当前课程知识库版本不完整')
        active['vector_path'] = str(vector_path)
        return catalog_path, active

    def course_outline(self) -> dict[str, Any]:
        catalog_path, active = self.paths()
        with sqlite3.connect(f'file:{catalog_path.as_posix()}?mode=ro', uri=True) as connection:
            rows = connection.execute("""
                SELECT chapter_no,
                       COUNT(DISTINCT file_id),
                       SUM(CASE WHEN collection_role='core' THEN 1 ELSE 0 END),
                       SUM(CASE WHEN collection_role='solutions' THEN 1 ELSE 0 END)
                FROM chunk
                GROUP BY chapter_no
                ORDER BY chapter_no
                """).fetchall()
        return {
            'course': 'Python程序设计基础教程（微课版）',
            'build_id': active['build_id'],
            'chapters': [
                {
                    'chapter_no': chapter_no,
                    'chapter_title': CHAPTER_TITLES[chapter_no],
                    'files': file_count,
                    'core_chunks': core_chunks,
                    'solution_chunks': solution_chunks,
                }
                for chapter_no, file_count, core_chunks, solution_chunks in rows
            ],
        }

    def chapter_materials(self, chapter_no: int, resource_type: str = 'all') -> dict[str, Any]:
        if chapter_no not in CHAPTER_TITLES:
            raise ValueError('章节编号必须是0到15')
        normalized_type = normalize_resource_type(resource_type)
        catalog_path, active = self.paths()
        clauses = ['chapter_no=?', "resource_type!='exercise_answer'"]
        params: list[Any] = [chapter_no]
        if normalized_type != 'all':
            clauses.append('resource_type=?')
            params.append(normalized_type)
        where = ' AND '.join(clauses)
        with sqlite3.connect(f'file:{catalog_path.as_posix()}?mode=ro', uri=True) as connection:
            files = connection.execute(
                f"""
                SELECT relative_path, resource_type, parse_status, issue
                FROM source_file
                WHERE {where}
                ORDER BY resource_type, relative_path
                """,
                params,
            ).fetchall()
            chunks = connection.execute(
                f"""
                SELECT resource_type, COUNT(*)
                FROM chunk
                WHERE chapter_no=? AND collection_role='core'
                {'AND resource_type=?' if normalized_type != 'all' else ''}
                GROUP BY resource_type
                ORDER BY resource_type
                """,
                params,
            ).fetchall()
        return {
            'build_id': active['build_id'],
            'chapter_no': chapter_no,
            'chapter_title': CHAPTER_TITLES[chapter_no],
            'resource_type': normalized_type,
            'chunk_counts': dict(chunks),
            'materials': [
                {
                    'source_path': path,
                    'resource_type': item_type,
                    'status': status,
                    **({'issue': issue} if issue else {}),
                }
                for path, item_type, status, issue in files
            ],
            'answer_policy': '本工具不返回参考答案正文。',
        }

    def sample_exercises(self, chapter_no: int, count: int = 3, seed: int = 0) -> dict[str, Any]:
        if chapter_no not in range(1, 16):
            raise ValueError('抽题章节必须是1到15')
        if not 1 <= count <= 5:
            raise ValueError('抽题数量必须是1到5')
        _, active = self.paths()
        import chromadb

        client = chromadb.PersistentClient(path=active['vector_path'])
        collection = client.get_collection(active['core_collection'])
        result = collection.get(
            where={
                '$and': [
                    {'chapter_no': {'$eq': chapter_no}},
                    {'resource_type': {'$eq': 'exercise_question'}},
                ]
            },
            include=['documents', 'metadatas'],
        )
        candidates = [
            {'document': document, 'metadata': metadata or {}}
            for document, metadata in zip(result.get('documents') or [], result.get('metadatas') or [])
            if document
        ]
        if not candidates:
            raise RuntimeError(f'第{chapter_no}章没有可用的习题题目')
        if seed == 0:
            digest = hashlib.sha256(f'{dt.date.today().isoformat()}:{chapter_no}'.encode()).digest()
            seed = int.from_bytes(digest[:8], 'big')
        selected = random.Random(seed).sample(candidates, k=min(count, len(candidates)))
        return {
            'chapter_no': chapter_no,
            'chapter_title': CHAPTER_TITLES[chapter_no],
            'count': len(selected),
            'exercises': [
                {
                    'index': index,
                    'source': item['metadata'].get('source'),
                    'page_start': item['metadata'].get('page_start'),
                    'page_end': item['metadata'].get('page_end'),
                    'content': item['document'],
                }
                for index, item in enumerate(selected, start=1)
            ],
            'answer_policy': '未读取参考答案；请先让学生独立作答，再提供分步骤反馈。',
        }
