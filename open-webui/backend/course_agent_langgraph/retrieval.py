from __future__ import annotations

import asyncio
import json
import re
import threading
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
) -> list[RetrievedChunk]:
    """Hybrid-search only the active core collection with vector and BM25 ranks."""
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

    result_limit = max(1, min(top_k, 12))
    candidate_limit = min(max(result_limit * 4, 20), 48)
    lexical_terms = _lexical_query_terms(query)

    def search() -> list[tuple[str, dict[str, Any], float]]:
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
            return []

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
                ][:result_limit]
                return [(*rows[item_id], 1.0) for item_id in trusted_ids]

        fused = _weighted_rrf(
            vector_ids,
            bm25_ids,
            bm25_weight=bounded_bm25_weight,
            limit=candidate_limit,
        )
        fused = _promote_precise_bm25_anchor(query, fused, bm25_ids)
        fused = _promote_definition_anchor(query, fused, bm25_ids, rows)
        fused = _expand_neighbor_context(fused, rows, query, result_limit)
        return [(*rows[item_id], score) for item_id, score in fused if item_id in rows]

    candidates = await asyncio.to_thread(search)
    chunks: list[RetrievedChunk] = []
    seen: set[tuple[str, int | None, str]] = set()

    for content, metadata, score in candidates:
        if not content:
            continue
        if score < min_score:
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
                'ordinal': metadata.get('ordinal'),
                'section_title': metadata.get('section_title', ''),
                'score': round(score, 4),
            }
        )
        if len(chunks) >= result_limit:
            break
    return chunks
