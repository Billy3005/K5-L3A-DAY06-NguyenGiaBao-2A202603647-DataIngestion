"""PostgreSQL + pgvector store: persistent vectors, metadata filters in SQL, cosine ranking.

Search is EXACT (sequential scan, no HNSW/IVFFlat index): the corpus has < 1,000
chunks per index, and exact search avoids approximate-index recall loss when a
WHERE filter is combined with ORDER BY distance.
"""
import hashlib
import json
from typing import Any

import psycopg
from pgvector.psycopg import register_vector

from .models import Chunk

FILTERABLE = {"chapter": "chapter", "section": "section", "document_id": "document_id"}

SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS chunks (
    strategy        text        NOT NULL,   -- index namespace: 'A' or 'B' (C reuses 'B')
    chunk_id        text        NOT NULL,
    document_id     text        NOT NULL,
    source          text        NOT NULL,
    page            integer     NOT NULL,   -- physical PDF page, 1-based
    chapter         integer     NOT NULL,   -- filter field (from PDF outline)
    chapter_title   text        NOT NULL,
    section         text        NOT NULL,
    start_char      integer     NOT NULL,
    end_char        integer     NOT NULL,
    text            text        NOT NULL,
    content_hash    text        NOT NULL,   -- sha256(model + text): detects changed chunks
    embedding_model text        NOT NULL,
    embedding       vector({dim}) NOT NULL,
    ingested_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (strategy, chunk_id)
);
CREATE INDEX IF NOT EXISTS chunks_strategy_chapter ON chunks (strategy, chapter);
"""


def content_hash(model_name: str, chunk: Chunk) -> str:
    """Hash of everything stored for a chunk: model, text and traceability metadata."""
    m = chunk.metadata
    key = [model_name, chunk.document_id, chunk.source, chunk.page, m["chapter"], m["chapter_title"],
           m["section"], m["start_char"], m["end_char"], chunk.text]
    return hashlib.sha256(json.dumps(key, ensure_ascii=False).encode("utf-8")).hexdigest()


class PgVectorStore:
    def __init__(self, database_url: str, dimensions: int) -> None:
        if not database_url:
            raise ValueError("DATABASE_URL missing (copy .env.example to .env)")
        self.database_url = database_url
        self.dimensions = dimensions

    def _connect(self) -> psycopg.Connection:
        conn = psycopg.connect(self.database_url, connect_timeout=5)
        register_vector(conn)
        return conn

    def create_schema(self) -> None:
        with psycopg.connect(self.database_url, connect_timeout=5) as conn:
            conn.execute(SCHEMA.format(dim=int(self.dimensions)))
            existing = conn.execute(
                "SELECT atttypmod FROM pg_attribute WHERE attrelid = 'chunks'::regclass AND attname = 'embedding'"
            ).fetchone()[0]
            if existing != self.dimensions:
                raise RuntimeError(f"table has vector({existing}) but model has {self.dimensions} dims")

    def existing_hashes(self, strategy: str) -> dict[str, str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT chunk_id, content_hash FROM chunks WHERE strategy = %s", (strategy,))
            return dict(rows.fetchall())

    def count(self, strategy: str) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT count(*) FROM chunks WHERE strategy = %s", (strategy,)).fetchone()[0]

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float] | None],
               model_name: str) -> dict[str, int]:
        """Idempotent sync of `chunks` (the COMPLETE chunk set of their documents) into `strategy`.

        * new chunk_id -> INSERT; same id + same hash -> untouched; same id + new hash -> UPDATE
        * chunks of these documents that are no longer produced -> DELETE (obsolete)
        `vectors[i]` may be None only for chunks whose hash is unchanged (not re-embedded).
        Runs in one transaction: a failure leaves the previous index intact.
        """
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors length differ")
        if len({c.chunk_id for c in chunks}) != len(chunks):
            raise ValueError("duplicate chunk ids in batch")
        old = self.existing_hashes(strategy)
        stats = {"inserted": 0, "updated": 0, "unchanged": 0, "deleted": 0}
        with self._connect() as conn, conn.transaction():
            for chunk, vector in zip(chunks, vectors):
                digest = content_hash(model_name, chunk)
                if old.get(chunk.chunk_id) == digest:
                    stats["unchanged"] += 1
                    continue
                if vector is None or len(vector) != self.dimensions:
                    raise ValueError(f"{chunk.chunk_id}: missing or wrong-size vector")
                m = chunk.metadata
                conn.execute(
                    """INSERT INTO chunks (strategy, chunk_id, document_id, source, page, chapter, chapter_title,
                                           section, start_char, end_char, text, content_hash, embedding_model, embedding)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector)
                       ON CONFLICT (strategy, chunk_id) DO UPDATE SET
                         document_id = EXCLUDED.document_id, source = EXCLUDED.source, page = EXCLUDED.page,
                         chapter = EXCLUDED.chapter, chapter_title = EXCLUDED.chapter_title,
                         section = EXCLUDED.section, start_char = EXCLUDED.start_char, end_char = EXCLUDED.end_char,
                         text = EXCLUDED.text, content_hash = EXCLUDED.content_hash,
                         embedding_model = EXCLUDED.embedding_model, embedding = EXCLUDED.embedding,
                         ingested_at = now()""",
                    (strategy, chunk.chunk_id, chunk.document_id, chunk.source, chunk.page, m["chapter"],
                     m["chapter_title"], m["section"], m["start_char"], m["end_char"], chunk.text,
                     digest, model_name, vector))
                stats["updated" if chunk.chunk_id in old else "inserted"] += 1
            documents = sorted({c.document_id for c in chunks})
            deleted = conn.execute(
                "DELETE FROM chunks WHERE strategy = %s AND document_id = ANY(%s) AND NOT (chunk_id = ANY(%s))",
                (strategy, documents, [c.chunk_id for c in chunks]))
            stats["deleted"] = deleted.rowcount
        return stats

    def search(self, strategy: str, query_vector: list[float], top_k: int = 3,
               filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Top-k by cosine similarity, with optional metadata filters applied in SQL.

        Only whitelisted metadata columns can be filtered; values are always bound
        parameters (never interpolated into SQL).
        """
        if len(query_vector) != self.dimensions:
            raise ValueError("query vector has wrong dimensions")
        where, params = ["strategy = %s"], [strategy]
        for key, value in (filters or {}).items():
            if key not in FILTERABLE:
                raise ValueError(f"filter on '{key}' is not allowed")
            where.append(f"{FILTERABLE[key]} = %s")
            params.append(value)
        sql = f"""SELECT chunk_id, document_id, source, page, chapter, chapter_title, section,
                         start_char, end_char, text, 1 - (embedding <=> %s::vector) AS score
                  FROM chunks WHERE {' AND '.join(where)}
                  ORDER BY embedding <=> %s::vector, chunk_id
                  LIMIT %s"""
        with self._connect() as conn:
            cur = conn.execute(sql, [query_vector, *params, query_vector, top_k])
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
