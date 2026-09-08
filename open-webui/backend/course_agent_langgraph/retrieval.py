from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
from functools import lru_cache
from typing import Any

from .course_data import CHAPTER_TITLES, CourseData, normalize_resource_type
from .state import RetrievedChunk

_EXHAUSTIVE_MARKERS = ('所有', '全部', '完整', '一览', '列出')
_QUERY_FILLER_WORDS = (
    'python语言中',
    'python中',
    'python语言',
    'python',
    '请依据课程资料',
    '根据课程资料',
    '课程资料',
    '请回答',
    '并给出来源',
    '给出来源',
    '有哪些',
    '是什么',
    '请问',
    '的',
    '中',
)

_BM25_STOP_TOKENS = {
    'python', '请问', '请依', '依据', '课程', '资料', '回答', '什么', '哪些',
    '如何', '怎么', '中的', '进行', '使用', '给出', '一下',
}
_NEIGHBOR_CONTEXT_MARKERS = (
    '步骤', '过程', '流程', '区别', '比较', '完整', '前后', '上下文', '如何',
    '怎么', '为什么', '什么是', '定义', '概念', '先', '再', '然后', 'dumps', 'loads',
)
_CORPUS_CACHE: dict[tuple[str, str, str], dict[str, Any]] = {}
_CORPUS_CACHE_LOCK = threading.Lock()
_DEFAULT_RERANK_MODEL = 'BAAI/bge-reranker-v2-m3'
_DEFAULT_RERANK_URL = 'https://api.siliconflow.cn/v1/rerank'
log = logging.getLogger(__name__)


def _is_exhaustive_request(query: str) -> bool:
    return any(marker in query.lower() for marker in _EXHAUSTIVE_MARKERS)


def _lexical_query_terms(query: str) -> list[str]:
    """Extract stable anchors for exhaustive/list questions.

    Dense retrieval can confuse nearby Chinese concepts such as “关键字” and
    “字典的键”.  Exact anchors are only added for questions asking for a full
    list, so ordinary semantic questions keep their existing retrieval path.
    """
    if not _is_exhaustive_request(query):
        return []

    normalized = re.sub(r'[\s，。！？、；：,.!?;:（）()]+', '', query.lower())
    focused = normalized
    for word in _QUERY_FILLER_WORDS:
        focused = focused.replace(word, '')

    terms: list[str] = []
    if len(focused) >= 2:
        terms.append(focused)

    concept = focused
    for marker in _EXHAUSTIVE_MARKERS:
        concept = concept.replace(marker, '')
    if len(concept) >= 2:
        terms.append(concept)

    # “关键字” and “保留字” are synonyms in course questions.  Keeping both
    # makes the retrieval robust to either wording without changing the data.
    if '关键字' in normalized or '保留字' in normalized:
        terms.extend(('所有关键字', '关键字', '保留字'))

    return list(dict.fromkeys(term for term in terms if len(term) >= 2))


def _lexical_relevance(content: str, terms: list[str], exhaustive: bool) -> float:
    text = content.lower()
    score = 0.0
    for term in terms:
        count = text.count(term.lower())
        if count:
            score += min(count, 5) * (2.0 + min(len(term), 8) / 4.0)
    if exhaustive and any(f'所有{term}' in text for term in terms if not term.startswith('所有')):
        score += 20.0
    if exhaustive and '表' in text and any(term in text for term in terms):
        score += 3.0
    return score


def _bm25_tokenize(text: str) -> list[str]:
    """Tokenize Chinese prose, Python identifiers and numbers for BM25."""
    normalized = re.sub(r'\bpep\s*[-_]?\s*8\b', 'pep8', text.lower())
    tokens = re.findall(r'[a-z_][a-z0-9_]*|\d+(?:\.\d+)*', normalized)
    for sequence in re.findall(r'[\u4e00-\u9fff]+', normalized):
        if len(sequence) == 1:
            tokens.append(sequence)
            continue
        tokens.extend(sequence[index : index + 2] for index in range(len(sequence) - 1))
        if len(sequence) >= 3:
            tokens.extend(sequence[index : index + 3] for index in range(len(sequence) - 2))
        if len(sequence) <= 12:
            tokens.append(sequence)
    return [token for token in tokens if token not in _BM25_STOP_TOKENS]


def _definition_subject(query: str) -> str:
    compact = re.sub(r'[\s，。！？、,.!?：:]+', '', query.lower())
    for pattern in (
        r'(?:在python中)?什么是([\u4e00-\u9fffA-Za-z_][\u4e00-\u9fffA-Za-z_0-9]{0,15})',
        r'([\u4e00-\u9fffA-Za-z_][\u4e00-\u9fffA-Za-z_0-9]{0,15})是什么',
        r'([\u4e00-\u9fffA-Za-z_][\u4e00-\u9fffA-Za-z_0-9]{0,15})的(?:基本)?定义',
    ):
        match = re.fullmatch(pattern, compact)
        if match:
            return match.group(1)
    return ''


def _bm25_query_text(query: str) -> str:
    subject = _definition_subject(query)
    return f'{query} {subject} 定义 基本定义 概念 调用' if subject else query


def _bm25_document_text(document: str, metadata: dict[str, Any] | None = None) -> str:
    """Do not let the identical course/source header dominate lexical ranking."""
    parts = document.split('\n\n', 1)
    body = parts[1] if len(parts) == 2 else document
    section_title = str((metadata or {}).get('section_title') or '')
    return f'{section_title} {section_title}\n{body}' if section_title else body


def _create_bm25(
    documents: list[str], metadatas: list[dict[str, Any]] | None = None
) -> Any:
    from rank_bm25 import BM25Okapi

    metadata_rows = metadatas or [{} for _ in documents]
    return BM25Okapi(
        [
            _bm25_tokenize(
                _bm25_document_text(
                    document,
                    metadata_rows[index] if index < len(metadata_rows) else {},
                )
            )
            for index, document in enumerate(documents)
        ]
    )


def _bm25_rank(
    query: str,
    ids: list[str],
    documents: list[str],
    limit: int,
    bm25: Any = None,
) -> list[str]:
    if not ids or not documents:
        return []
    query_tokens = _bm25_tokenize(_bm25_query_text(query))
    if not query_tokens:
        return []

    scores = (bm25 or _create_bm25(documents)).get_scores(query_tokens)
    ranked = sorted(
        (
            (item_id, float(scores[index]))
            for index, item_id in enumerate(ids)
            if index < len(scores) and float(scores[index]) > 0
        ),
        key=lambda item: item[1],
        reverse=True,
    )
    return [item_id for item_id, _ in ranked[:limit]]


def _cached_corpus(
    collection: Any,
    *,
    vector_path: str,
    collection_name: str,
    where: dict[str, Any] | None,
    include_bm25: bool,
) -> dict[str, Any]:
    key = (vector_path, collection_name, json.dumps(where, sort_keys=True, ensure_ascii=False))
    with _CORPUS_CACHE_LOCK:
        cached = _CORPUS_CACHE.get(key)
        if cached is None:
            kwargs: dict[str, Any] = {'include': ['documents', 'metadatas']}
            if where:
                kwargs['where'] = where
            corpus = collection.get(**kwargs)
            ids = list(corpus.get('ids') or [])
            documents = list(corpus.get('documents') or [])
            metadatas = list(corpus.get('metadatas') or [])
            cached = {
                'ids': ids,
                'documents': documents,
                'metadatas': metadatas,
                'bm25': None,
            }
            if len(_CORPUS_CACHE) >= 32:
                _CORPUS_CACHE.clear()
            _CORPUS_CACHE[key] = cached
        if include_bm25 and cached['bm25'] is None and cached['documents']:
            cached['bm25'] = _create_bm25(cached['documents'], cached['metadatas'])
        return cached


def _needs_neighbor_context(query: str) -> bool:
    lowered = query.lower()
    return any(marker in lowered for marker in _NEIGHBOR_CONTEXT_MARKERS)


def _dynamic_context_limit(query: str, maximum: int) -> int:
    """Choose how many evidence groups the answer model receives.

    A single result is too brittle for teaching questions, while sending every
    candidate adds noise.  Definitions stay concise; lists, comparisons and
    multi-step/code questions receive more independently reranked evidence.
    """
    bounded_maximum = max(1, min(maximum, 12))
    lowered = query.lower()
    if _is_exhaustive_request(query) or any(
        marker in lowered for marker in ('比较', '区别', '异同', '分别', '归纳', '总结')
    ):
        desired = 8
    elif any(
        marker in lowered
        for marker in ('代码', '示例', '步骤', '过程', '流程', '如何', '怎么', '实现', '调用')
    ):
        desired = 5
    elif _definition_subject(query):
        desired = 3
    else:
        desired = 5
    return min(desired, bounded_maximum)


@lru_cache(maxsize=4)
def _external_reranker(
    api_key: str,
    url: str,
    model: str,
    timeout: int,
) -> Any:
    from open_webui.retrieval.models.external import ExternalReranker

    return ExternalReranker(
        api_key=api_key,
        url=url,
        model=model,
        timeout=timeout,
    )


def _configured_reranking_function(request: Any, user: Any) -> tuple[Any, str]:
    """Resolve the course reranker without exposing or persisting its API key."""
    api_key = os.getenv('COURSE_RERANK_API_KEY', '').strip()
    if api_key:
        url = os.getenv('COURSE_RERANK_API_URL', _DEFAULT_RERANK_URL).strip()
        model = os.getenv('COURSE_RERANK_MODEL', _DEFAULT_RERANK_MODEL).strip()
        try:
            timeout = max(1, int(os.getenv('COURSE_RERANK_TIMEOUT', '30')))
        except ValueError:
            timeout = 30
        reranker = _external_reranker(api_key, url, model, timeout)
        return (
            lambda query, documents: reranker.predict(
                [(query, document.page_content) for document in documents],
                user=user,
            ),
            model,
        )

    app = getattr(request, 'app', None)
    state = getattr(app, 'state', None)
    native = getattr(state, 'RERANKING_FUNCTION', None)
    if native is None:
        return None, ''

    def call_native(query: str, documents: list[Any]) -> Any:
        try:
            return native(query, documents, user=user)
        except TypeError:
            return native(query, documents)

    return call_native, 'open-webui-reranker'


async def _rerank_candidates(
    request: Any,
    user: Any,
    query: str,
    candidates: list[tuple[str, str, dict[str, Any], float]],
    limit: int,
) -> tuple[list[tuple[str, str, dict[str, Any], float, float, float | None]], str]:
    """Rerank hybrid candidates, falling back to their RRF order on any error."""
    fallback = [
        (item_id, content, metadata, score, score, None)
        for item_id, content, metadata, score in candidates[:limit]
    ]
    reranking_function, model = _configured_reranking_function(request, user)
    if reranking_function is None or not candidates:
        return fallback, 'hybrid_rrf'

    from langchain_core.documents import Document

    documents = [
        Document(page_content=content, metadata={'candidate_id': item_id})
        for item_id, content, _, _ in candidates
    ]
    try:
        scores = await asyncio.to_thread(reranking_function, query, documents)
        if scores is None:
            raise RuntimeError('重排序服务未返回分数')
        normalized_scores = scores.tolist() if hasattr(scores, 'tolist') else list(scores)
        if len(normalized_scores) != len(candidates):
            raise RuntimeError(
                f'重排序分数数量不匹配：期望{len(candidates)}，实际{len(normalized_scores)}'
            )
        reranked = sorted(
            (
                (
                    item_id,
                    content,
                    metadata,
                    float(normalized_scores[index]),
                    fusion_score,
                    float(normalized_scores[index]),
                )
                for index, (item_id, content, metadata, fusion_score) in enumerate(candidates)
            ),
            key=lambda item: (-item[3], -item[4], item[0]),
        )
        return reranked[:limit], model or 'reranker'
    except Exception as exc:
        log.warning('Course reranking failed; using hybrid RRF order: %s', exc)
        return fallback, 'hybrid_rrf_fallback'


def _adjacent_member_ids(
    anchor_id: str,
    anchor_metadata: dict[str, Any],
    rows: dict[str, tuple[str, dict[str, Any]]],
    ranked_ids: set[str],
    used: set[str],
    include_neighbors: bool,
) -> list[str]:
    file_id = anchor_metadata.get('file_id')
    ordinal = anchor_metadata.get('ordinal')
    if not file_id or not isinstance(ordinal, int):
        return [anchor_id]
    adjacent = [
        item_id
        for item_id, (_, metadata) in rows.items()
        if item_id != anchor_id
        and item_id not in used
        and metadata.get('file_id') == file_id
        and isinstance(metadata.get('ordinal'), int)
        and abs(metadata['ordinal'] - ordinal) == 1
        and (include_neighbors or item_id in ranked_ids)
    ]
    return [anchor_id, *adjacent]


def _assemble_evidence_groups(
    ranked: list[tuple[str, str, dict[str, Any], float, float, float | None]],
    rows: dict[str, tuple[str, dict[str, Any]]],
    query: str,
    limit: int,
) -> list[tuple[str, dict[str, Any], float, float, float | None]]:
    """Group adjacent chunks so each final item is a coherent evidence passage."""
    if not ranked:
        return []
    ranked_ids = {item[0] for item in ranked}
    used: set[str] = set()
    groups: list[tuple[str, dict[str, Any], float, float, float | None]] = []
    include_neighbors = _needs_neighbor_context(query)

    for anchor_id, anchor_content, anchor_metadata, score, fusion_score, rerank_score in ranked:
        if anchor_id in used:
            continue
        ordinal = anchor_metadata.get('ordinal')
        member_ids = _adjacent_member_ids(
            anchor_id,
            anchor_metadata,
            rows,
            ranked_ids,
            used,
            include_neighbors,
        )

        member_ids.sort(
            key=lambda item_id: (
                rows.get(item_id, ('', {}))[1].get('ordinal')
                if isinstance(rows.get(item_id, ('', {}))[1].get('ordinal'), int)
                else ordinal or 0
            )
        )
        members = [rows.get(item_id, ('', {})) for item_id in member_ids]
        contents = [content for content, _ in members if content]
        if not contents:
            contents = [anchor_content]
        merged_content = '\n\n--- 相邻知识块 ---\n\n'.join(dict.fromkeys(contents))
        merged_metadata = dict(anchor_metadata)
        pages_start = [metadata.get('page_start') for _, metadata in members if metadata.get('page_start')]
        pages_end = [
            metadata.get('page_end') or metadata.get('page_start')
            for _, metadata in members
            if metadata.get('page_end') or metadata.get('page_start')
        ]
        if pages_start:
            merged_metadata['page_start'] = min(pages_start)
        if pages_end:
            merged_metadata['page_end'] = max(pages_end)
        lines_start = [metadata.get('line_start') for _, metadata in members if metadata.get('line_start')]
        lines_end = [
            metadata.get('line_end') or metadata.get('line_start')
            for _, metadata in members
            if metadata.get('line_end') or metadata.get('line_start')
        ]
        if lines_start:
            merged_metadata['line_start'] = min(lines_start)
        if lines_end:
            merged_metadata['line_end'] = max(lines_end)
        merged_metadata['group_size'] = len(member_ids)
        merged_metadata['chunk_ids'] = ','.join(member_ids)
        used.update(member_ids)
        groups.append((merged_content, merged_metadata, score, fusion_score, rerank_score))
        if len(groups) >= limit:
            break
    return groups


def _expand_neighbor_context(
    ranked: list[tuple[str, float]],
    rows: dict[str, tuple[str, dict[str, Any]]],
    query: str,
    limit: int,
) -> list[tuple[str, float]]:
    """Put nearby chunks from the strongest source beside a process/comparison hit."""
    if not ranked or not _needs_neighbor_context(query):
        return ranked[:limit]
    anchor_id, anchor_score = ranked[0]
    anchor_metadata = rows.get(anchor_id, ('', {}))[1]
    file_id = anchor_metadata.get('file_id')
    ordinal = anchor_metadata.get('ordinal')
    if not file_id or not isinstance(ordinal, int):
        return ranked[:limit]

    nearby = sorted(
        (
            (item_id, abs(int(metadata.get('ordinal')) - ordinal), int(metadata.get('ordinal')))
            for item_id, (_, metadata) in rows.items()
            if item_id != anchor_id
            and metadata.get('file_id') == file_id
            and isinstance(metadata.get('ordinal'), int)
            and 1 <= abs(int(metadata['ordinal']) - ordinal) <= 2
        ),
        key=lambda item: (item[1], item[2]),
    )
    expanded: list[tuple[str, float]] = [(anchor_id, anchor_score)]
    seen = {anchor_id}
    for item_id, distance, _ in nearby:
        expanded.append((item_id, round(anchor_score * (0.78 if distance == 1 else 0.62), 6)))
        seen.add(item_id)
        if len(expanded) >= limit:
            return expanded
    for item_id, score in ranked:
        if item_id not in seen:
            expanded.append((item_id, score))
            seen.add(item_id)
        if len(expanded) >= limit:
            break
    return expanded


def _weighted_rrf(
    vector_ids: list[str],
    bm25_ids: list[str],
    bm25_weight: float,
    limit: int,
) -> list[tuple[str, float]]:
    """Fuse vector and BM25 ranks using normalized weighted RRF."""
    rank_constant = 60.0
    bounded_bm25_weight = min(max(bm25_weight, 0.0), 1.0)
    vector_weight = 1.0 - bounded_bm25_weight
    scores: dict[str, float] = {}
    best_rank: dict[str, int] = {}

    for weight, ranked_ids in (
        (vector_weight, vector_ids),
        (bounded_bm25_weight, bm25_ids),
    ):
        if weight <= 0:
            continue
        for rank, item_id in enumerate(ranked_ids, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + weight / (
                rank_constant + rank
            )
            best_rank[item_id] = min(best_rank.get(item_id, rank), rank)

    ideal_score = 1.0 / (rank_constant + 1.0)
    ranked = sorted(
        scores,
        key=lambda item_id: (-scores[item_id], best_rank[item_id], item_id),
    )[:limit]
    return [(item_id, min(1.0, scores[item_id] / ideal_score)) for item_id in ranked]


def _promote_precise_bm25_anchor(
    query: str,
    fused: list[tuple[str, float]],
    bm25_ids: list[str],
) -> list[tuple[str, float]]:
    """Keep exact lexical anchors for short follow-ups and dotted Python APIs."""
    if not bm25_ids:
        return fused
    compact = re.sub(r'\s+', '', query)
    dotted_identifiers = re.findall(r'\b[a-z_]\w*(?:\.[a-z_]\w*)+\b', query.lower())
    if len(compact) > 30 and not dotted_identifiers:
        return fused
    anchor = bm25_ids[0]
    existing_score = next((score for item_id, score in fused if item_id == anchor), 1.0)
    return [(anchor, max(1.0, existing_score))] + [
        (item_id, score) for item_id, score in fused if item_id != anchor
    ]


def _promote_definition_anchor(
    query: str,
    fused: list[tuple[str, float]],
    bm25_ids: list[str],
    rows: dict[str, tuple[str, dict[str, Any]]],
) -> list[tuple[str, float]]:
    """Prefer the page containing the actual definition/syntax over later examples."""
    subject = _definition_subject(query)
    if not subject:
        return fused
    candidates: list[tuple[int, int, str]] = []
    for rank, item_id in enumerate(bm25_ids[:12], start=1):
        content, metadata = rows.get(item_id, ('', {}))
        title = str(metadata.get('section_title') or '')
        prefix = content.split('\n\n', 1)[-1][:800]
        score = 0
        if f'定义{subject}的语法' in prefix:
            score += 20
        if '基本定义' in prefix or '基本定义' in title:
            score += 8
        if subject in title:
            score += 4
        if f'{subject}是' in prefix or f'{subject}指' in prefix:
            score += 12
        if score:
            candidates.append((score, -rank, item_id))
    if not candidates:
        return fused
    anchor = max(candidates)[2]
    existing_score = next((score for item_id, score in fused if item_id == anchor), 1.0)
    return [(anchor, max(1.0, existing_score))] + [
        (item_id, score) for item_id, score in fused if item_id != anchor
    ]


async def retrieve_core_chunks(  # noqa: C901 - vector and lexical paths share filtering and result shaping
    request: Any,
    user: Any,
    course_data: CourseData,
    query: str,
    *,
    chapter_no: int | None = None,
    resource_type: str = 'all',
    top_k: int = 5,
    min_score: float = 0.0,
    bm25_weight: float = 0.3,
    candidate_k: int = 40,
    rerank_top_n: int = 12,
    rerank_min_score: float = 0.0,
) -> list[RetrievedChunk]:
    """Hybrid-retrieve, rerank and group evidence from the active core collection."""
    from open_webui.config import RAG_EMBEDDING_QUERY_PREFIX

    _, active = course_data.paths()
    bounded_bm25_weight = min(max(bm25_weight, 0.0), 1.0)
    vector = None
    if bounded_bm25_weight < 1.0:
        embedding_function = getattr(request.app.state, 'EMBEDDING_FUNCTION', None)
        if embedding_function is None:
            raise RuntimeError('Open WebUI 嵌入模型尚未初始化')
        vector = await embedding_function(query, prefix=RAG_EMBEDDING_QUERY_PREFIX, user=user)

    filters: list[dict[str, Any]] = []
    if chapter_no is not None:
        filters.append({'chapter_no': {'$eq': chapter_no}})
    normalized_type = normalize_resource_type(resource_type)
    if normalized_type != 'all':
        filters.append({'resource_type': {'$eq': normalized_type}})
    where = filters[0] if len(filters) == 1 else {'$and': filters} if filters else None

    result_limit = _dynamic_context_limit(query, top_k)
    candidate_limit = min(max(candidate_k, result_limit * 4, 20), 80)
    rerank_limit = min(max(rerank_top_n, result_limit), candidate_limit)
    lexical_terms = _lexical_query_terms(query)

    def search() -> tuple[
        list[tuple[str, str, dict[str, Any], float]],
        dict[str, tuple[str, dict[str, Any]]],
    ]:
        import chromadb

        client = chromadb.PersistentClient(path=active['vector_path'])
        collection = client.get_collection(active['core_collection'])

        corpus = _cached_corpus(
            collection,
            vector_path=active['vector_path'],
            collection_name=active['core_collection'],
            where=where,
            include_bm25=bounded_bm25_weight > 0.0,
        )
        corpus_ids = corpus['ids']
        corpus_documents = corpus['documents']
        corpus_metadatas = corpus['metadatas']
        if not corpus_ids:
            return [], {}

        vector_ids: list[str] = []
        if vector is not None:
            kwargs: dict[str, Any] = {
                'query_embeddings': [vector],
                'n_results': min(candidate_limit, len(corpus_ids)),
                'include': ['documents', 'metadatas', 'distances'],
            }
            if where:
                kwargs['where'] = where
            vector_response = collection.query(**kwargs)
            vector_ids = list((vector_response.get('ids') or [[]])[0])
        bm25_ids = (
            _bm25_rank(
                query,
                corpus_ids,
                corpus_documents,
                candidate_limit,
                bm25=corpus['bm25'],
            )
            if bounded_bm25_weight > 0.0
            else []
        )

        rows = {
            item_id: (
                corpus_documents[index],
                dict(corpus_metadatas[index] or {})
                if index < len(corpus_metadatas)
                else {},
            )
            for index, item_id in enumerate(corpus_ids)
            if index < len(corpus_documents) and corpus_documents[index]
        }

        # Preserve the complete-list safeguard: when one or more documents
        # contain a substantially stronger exact phrase match, return those
        # documents without adding loosely related neighbors.
        if lexical_terms:
            exact_ranked = sorted(
                (
                    (item_id, _lexical_relevance(content, lexical_terms, True))
                    for item_id, (content, _) in rows.items()
                ),
                key=lambda item: item[1],
                reverse=True,
            )
            if exact_ranked and exact_ranked[0][1] >= 8.0:
                strongest_score = exact_ranked[0][1]
                trusted_ids = [
                    item_id
                    for item_id, score in exact_ranked
                    if score >= max(8.0, strongest_score * 0.6)
                ][:rerank_limit]
                return [
                    (item_id, *rows[item_id], 1.0) for item_id in trusted_ids
                ], rows

        fused = _weighted_rrf(
            vector_ids,
            bm25_ids,
            bm25_weight=bounded_bm25_weight,
            limit=candidate_limit,
        )
        fused = _promote_precise_bm25_anchor(query, fused, bm25_ids)
        fused = _promote_definition_anchor(query, fused, bm25_ids, rows)
        return [
            (item_id, *rows[item_id], score)
            for item_id, score in fused
            if item_id in rows
        ], rows

    candidates, rows = await asyncio.to_thread(search)
    reranked, ranking_method = await _rerank_candidates(
        request,
        user,
        query,
        candidates,
        rerank_limit,
    )
    evidence_groups = _assemble_evidence_groups(
        reranked,
        rows,
        query,
        result_limit,
    )
    chunks: list[RetrievedChunk] = []
    seen: set[tuple[str, int | None, str]] = set()

    for content, metadata, score, fusion_score, rerank_score in evidence_groups:
        if not content:
            continue
        if score < min_score:
            continue
        if rerank_score is not None and rerank_score < rerank_min_score:
            continue
        source = metadata.get('source') or metadata.get('source_path') or '课程知识库'
        key = (source, metadata.get('page_start'), content[:80])
        if key in seen:
            continue
        seen.add(key)
        chunk_chapter = metadata.get('chapter_no')
        chunks.append(
            {
                'content': content,
                'source': source,
                'chapter_no': chunk_chapter,
                'chapter_title': CHAPTER_TITLES.get(chunk_chapter, ''),
                'resource_type': metadata.get('resource_type', ''),
                'page_start': metadata.get('page_start'),
                'page_end': metadata.get('page_end'),
                'line_start': metadata.get('line_start'),
                'line_end': metadata.get('line_end'),
                'ordinal': metadata.get('ordinal'),
                'section_title': metadata.get('section_title', ''),
                'score': round(score, 4),
                'fusion_score': round(fusion_score, 4),
                'rerank_score': round(rerank_score, 4) if rerank_score is not None else None,
                'ranking_method': ranking_method,
                'group_size': metadata.get('group_size', 1),
            }
        )
        if len(chunks) >= result_limit:
            break
    return chunks
