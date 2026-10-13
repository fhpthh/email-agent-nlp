import logging
import re
from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID
from sqlalchemy import text

from src.emailagent.config import settings
from src.emailagent.domain.models import EmailMessageSnippet, RetrievedThreadContext
from src.emailagent.utils.stopwords import remove_vietnamese_stopwords
from .base import BaseRepository

logger = logging.getLogger("emailagent.db.repository.search")


class SearchRepository(BaseRepository):
    """Repository phụ trách Vector Search, Full-Text Search và thuật toán RRF."""

    async def get_threads_missing_embeddings(self, limit: int = 50) -> List[dict]:
        query = text("""
            SELECT id, subject, category, summary
            FROM threads
            WHERE summary IS NOT NULL
              AND embedding IS NULL
            ORDER BY created_at DESC
            LIMIT :limit;
        """)
        result = await self._session.execute(query, {"limit": limit})
        return [dict(row._mapping) for row in result.fetchall()]

    async def update_thread_embedding(self, thread_id: UUID, embedding: List[float]) -> None:
        vector_str = f"[{','.join(f'{x:.6f}' for x in embedding)}]"
        query = text("""
            UPDATE threads
            SET embedding = CAST(:embedding AS vector)
            WHERE id = :thread_id;
        """)
        await self._session.execute(query, {
            "thread_id": thread_id,
            "embedding": vector_str
        })

    async def _fetch_thread_messages_snippets(
        self,
        thread_ids: List[UUID],
        max_per_thread: int = 3
    ) -> Dict[UUID, List[EmailMessageSnippet]]:
        if not thread_ids:
            return {}

        query = text("""
            WITH RankedEmails AS (
                SELECT 
                    e.id AS message_id,
                    e.thread_id,
                    e.sender,
                    e.date_sent,
                    SUBSTRING(COALESCE(e.clean_body, '') FROM 1 FOR 800) AS body_snippet,
                    ROW_NUMBER() OVER(PARTITION BY e.thread_id ORDER BY e.date_sent DESC) as rank_idx
                FROM emails e
                WHERE e.thread_id = ANY(:thread_ids)
            )
            SELECT message_id, thread_id, sender, date_sent, body_snippet
            FROM RankedEmails
            WHERE rank_idx <= :max_per_thread
            ORDER BY thread_id, date_sent ASC;
        """)

        result = await self._session.execute(query, {
            "thread_ids": thread_ids,
            "max_per_thread": max_per_thread
        })
        rows = result.fetchall()

        mapping: Dict[UUID, List[EmailMessageSnippet]] = {tid: [] for tid in thread_ids}
        for row in rows:
            mapping[row.thread_id].append(
                EmailMessageSnippet(
                    message_id=str(row.message_id),
                    sender=row.sender,
                    date_sent=row.date_sent,
                    body_snippet=row.body_snippet or ""
                )
            )
        return mapping

    async def search_similar_threads(
        self,
        query_embedding: List[float],
        query_text: Optional[str] = None,
        account_id: Optional[UUID] = None,
        date_after: Optional[datetime] = None,
        top_k: int = 8,
        threshold: float = 0.50
    ) -> List[RetrievedThreadContext]:
        """
        Tìm kiếm Hybrid kết hợp pgvector và Full-Text Search.
        Hỗ trợ lọc theo mốc thời gian date_after và lọc đa dạng hóa Diversity.
        """
        vector_str = f"[{','.join(f'{x:.6f}' for x in query_embedding)}]"
        raw_text_query = (query_text or "").strip()
        # Lọc hư từ (Stopwords) ở tầng Application trước khi đẩy vào FTS
        clean_text_query = remove_vietnamese_stopwords(raw_text_query)

        # 1. Vector Search Query
        vector_query = text("""
            SELECT 
                t.id AS thread_id,
                t.subject,
                t.category,
                t.summary,
                t.last_message_at,
                (1 - (t.embedding <=> CAST(:query_vector AS vector))) AS similarity_score
            FROM threads t
            WHERE t.embedding IS NOT NULL
              AND (CAST(:account_id AS uuid) IS NULL OR t.account_id = CAST(:account_id AS uuid))
              AND (CAST(:date_after AS timestamptz) IS NULL OR t.last_message_at >= CAST(:date_after AS timestamptz))
            ORDER BY similarity_score DESC
            LIMIT :vector_limit;
        """)

        vector_res = await self._session.execute(vector_query, {
            "query_vector": vector_str,
            "account_id": account_id,
            "date_after": date_after,
            "vector_limit": top_k * 3
        })
        vector_rows = vector_res.fetchall()

        # 2. Sparse Full-Text Search Query (Đã tối ưu hóa Stopwords, Field Weighting và Length Normalization)
        fts_rows = []
        if clean_text_query:
            fts_query = text("""
                SELECT 
                    e.thread_id,
                    t.subject,
                    t.category,
                    t.summary,
                    t.last_message_at,
                    ts_rank_cd(
                        '{0.1, 0.2, 0.4, 1.0}',
                        e.tsv,
                        plainto_tsquery('simple', clean_fts_vietnamese(:text_query)),
                        32
                    ) AS fts_score
                FROM emails e
                JOIN threads t ON e.thread_id = t.id
                WHERE e.tsv @@ plainto_tsquery('simple', clean_fts_vietnamese(:text_query))
                  AND (CAST(:account_id AS uuid) IS NULL OR t.account_id = CAST(:account_id AS uuid))
                  AND (CAST(:date_after AS timestamptz) IS NULL OR t.last_message_at >= CAST(:date_after AS timestamptz))
                ORDER BY fts_score DESC
                LIMIT :fts_limit;
            """)
            fts_res = await self._session.execute(fts_query, {
                "text_query": clean_text_query,
                "account_id": account_id,
                "date_after": date_after,
                "fts_limit": top_k * 3
            })
            fts_rows = fts_res.fetchall()

        # 3. Reciprocal Rank Fusion (RRF Algorithm)
        rrf_scores: Dict[UUID, float] = {}
        candidate_meta: Dict[UUID, dict] = {}

        for rank_idx, row in enumerate(vector_rows):
            tid = row.thread_id
            score = float(row.similarity_score)
            rrf_scores[tid] = rrf_scores.get(tid, 0.0) + (1.0 / (60 + rank_idx + 1))
            if tid not in candidate_meta:
                candidate_meta[tid] = {
                    "subject": row.subject,
                    "category": row.category,
                    "summary": row.summary,
                    "last_message_at": row.last_message_at,
                    "cosine_score": score
                }

        for rank_idx, row in enumerate(fts_rows):
            tid = row.thread_id
            rrf_scores[tid] = rrf_scores.get(tid, 0.0) + (1.0 / (60 + rank_idx + 1))
            if tid not in candidate_meta:
                candidate_meta[tid] = {
                    "subject": row.subject,
                    "category": row.category,
                    "summary": row.summary,
                    "last_message_at": row.last_message_at,
                    "cosine_score": 0.50
                }

        sorted_threads = sorted(rrf_scores.keys(), key=lambda t: rrf_scores[t], reverse=True)

        # 4. Diversity Deduplication:
        final_selected_ids: List[UUID] = []
        subject_counts: Dict[str, int] = {}

        for tid in sorted_threads:
            meta = candidate_meta[tid]
            clean_subj = re.sub(r"[^\w\s]", "", (meta["subject"] or "").lower()).strip()

            # Mỗi chủ đề lặp lại tối đa 2 lần
            if subject_counts.get(clean_subj, 0) >= 2:
                continue

            cosine_score = meta["cosine_score"]
            if cosine_score >= threshold or tid in [r.thread_id for r in fts_rows]:
                final_selected_ids.append(tid)
                subject_counts[clean_subj] = subject_counts.get(clean_subj, 0) + 1
            elif len(final_selected_ids) == 0 and cosine_score >= getattr(settings, "RAG_MIN_FALLBACK_THRESHOLD", 0.40):
                final_selected_ids.append(tid)
                subject_counts[clean_subj] = subject_counts.get(clean_subj, 0) + 1

            if len(final_selected_ids) >= top_k:
                break

        if not final_selected_ids:
            return []

        max_snippets = getattr(settings, "RAG_MAX_MESSAGES_PER_THREAD", 3)
        messages_mapping = await self._fetch_thread_messages_snippets(final_selected_ids, max_per_thread=max_snippets)

        contexts = []
        for tid in final_selected_ids:
            meta = candidate_meta[tid]
            contexts.append(
                RetrievedThreadContext(
                    thread_id=tid,
                    subject=meta["subject"] or "(No title)",
                    category=meta["category"] or "uncategorized",
                    summary=meta["summary"] or "",
                    similarity_score=meta["cosine_score"],
                    last_message_at=meta["last_message_at"],
                    messages=messages_mapping.get(tid, [])
                )
            )
        return contexts