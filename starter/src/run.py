"""Pipeline entry point.

  python -m src.run ingest                 # chunk + embed + upsert indexes A and B (idempotent)
  python -m src.run query --strategy C --chapter 4 "your question"

Strategies are defined in src/config.py. C reuses index B and only adds a filter.
"""
import argparse
import csv
import os
import platform
import time
from datetime import datetime, timezone

from dotenv import load_dotenv

from .chunking import build_chunks
from .config import EMBEDDING_DIM, PAGES_JSONL, RESULTS, STARTER, STRATEGIES, TOP_K
from .embeddings import E5Embedder
from .ingestion import read_pages_jsonl
from .store import PgVectorStore, content_hash

INGEST_LOG = RESULTS / "ingest_runs.csv"


def get_store() -> PgVectorStore:
    load_dotenv(STARTER / ".env")
    store = PgVectorStore(os.getenv("DATABASE_URL", ""), EMBEDDING_DIM)
    store.create_schema()
    return store


def ingest(store: PgVectorStore, embedder: E5Embedder, index: str) -> dict:
    """Chunk the corpus for `index`, embed only new/changed chunks, sync to pgvector."""
    cfg = next(c for c in STRATEGIES.values() if c["index"] == index)
    t0 = time.perf_counter()
    pages = read_pages_jsonl(PAGES_JSONL)
    chunks = build_chunks(pages, cfg)
    t1 = time.perf_counter()
    old = store.existing_hashes(index)
    todo = [i for i, c in enumerate(chunks) if old.get(c.chunk_id) != content_hash(embedder.model_name, c)]
    vectors: list = [None] * len(chunks)
    if todo:
        for i, vec in zip(todo, embedder.embed_documents([chunks[i].text for i in todo])):
            vectors[i] = vec
    t2 = time.perf_counter()
    stats = store.upsert(index, chunks, vectors, embedder.model_name)
    t3 = time.perf_counter()
    row = {"run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "index": index,
           "chunks": len(chunks), "embedded": len(todo), **stats, "rows_in_db": store.count(index),
           "chunk_s": round(t1 - t0, 2), "embed_s": round(t2 - t1, 2), "db_s": round(t3 - t2, 2),
           "total_s": round(t3 - t0, 2), "cost_usd": 0.0, "model": embedder.model_name,
           "device": f"cpu ({platform.processor() or platform.machine()})"}
    new_file = not INGEST_LOG.exists()
    with INGEST_LOG.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        if new_file:
            writer.writeheader()
        writer.writerow(row)
    return row


def retrieve(store: PgVectorStore, embedder: E5Embedder, strategy: str, question: str,
             question_filter: dict | None) -> tuple[list[dict], dict | None]:
    """Top-k for one question. Only strategy C uses the filter, and only if the question has one."""
    cfg = STRATEGIES[strategy]
    applied = question_filter if (cfg["use_filter"] and question_filter) else None
    return store.search(cfg["index"], embedder.embed_query(question), TOP_K, applied), applied


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ingest")
    q = sub.add_parser("query")
    q.add_argument("question")
    q.add_argument("--strategy", choices=sorted(STRATEGIES), default="B")
    q.add_argument("--chapter", type=int)
    args = parser.parse_args()

    store, embedder = get_store(), E5Embedder()
    if args.cmd == "ingest":
        for index in ("A", "B"):
            print(ingest(store, embedder, index))
    else:
        hits, applied = retrieve(store, embedder, args.strategy, args.question,
                                 {"chapter": args.chapter} if args.chapter else None)
        print(f"strategy={args.strategy} filter={applied}")
        for rank, h in enumerate(hits, 1):
            print(f"#{rank} score={h['score']:.4f} {h['chunk_id']} p{h['page']} ch{h['chapter']} "
                  f"[{h['section'][:45]}]\n    {h['text'][:160]!r}")


if __name__ == "__main__":
    main()
