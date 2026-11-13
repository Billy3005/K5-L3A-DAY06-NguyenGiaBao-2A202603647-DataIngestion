"""Demonstrate idempotent re-ingest and changed-document handling in an isolated namespace.

Uses namespace 'reload_check' (never the real A/B indexes) with B-chunks of pages 84-85:
  1. ingest            -> all inserted
  2. ingest again      -> all unchanged (no duplicates, no re-embedding)
  3. edit page 85      -> one value edited + second half of the page removed
     ingest            -> changed chunks updated, vanished chunks deleted (no stale rows)
  4. cleanup namespace
Run from starter/:  python -m scripts.reingest_check   (output: results/reingest_check.txt)
"""
import copy

from src.chunking import by_paragraph
from src.config import PAGES_JSONL, RESULTS, STRATEGIES
from src.embeddings import E5Embedder
from src.ingestion import read_pages_jsonl
from src.run import get_store
from src.store import content_hash

NS = "reload_check"


def sync(store, embedder, pages):
    chunks = [c for p in pages for c in by_paragraph(p, STRATEGIES["B"]["max_size"])]
    old = store.existing_hashes(NS)
    todo = [i for i, c in enumerate(chunks) if old.get(c.chunk_id) != content_hash(embedder.model_name, c)]
    vectors = [None] * len(chunks)
    for i, v in zip(todo, embedder.embed_documents([chunks[i].text for i in todo]) if todo else []):
        vectors[i] = v
    stats = store.upsert(NS, chunks, vectors, embedder.model_name)
    return {"chunks": len(chunks), "embedded": len(todo), **stats, "rows_in_db": store.count(NS)}


def main() -> None:
    store, embedder = get_store(), E5Embedder()
    pages = [p for p in read_pages_jsonl(PAGES_JSONL) if p.page in (84, 85)]
    lines = []
    with store._connect() as conn:
        conn.execute("DELETE FROM chunks WHERE strategy = %s", (NS,))
    lines.append(f"1. first ingest      {sync(store, embedder, pages)}")
    lines.append(f"2. re-ingest same    {sync(store, embedder, pages)}")

    edited = copy.deepcopy(pages)
    p85 = edited[1]
    blocks = p85.metadata["blocks"]
    blocks = blocks[: len(blocks) // 2]                      # remove the second half of the page
    first_text = next(i for i, b in enumerate(blocks) if b["kind"] == "text" and len(b["text"]) > 200)
    blocks[first_text] = {**blocks[first_text],
                          "text": blocks[first_text]["text"].replace("$7.25", "$7.50")}  # edit a value
    p85.metadata["blocks"] = blocks
    p85.text = "\n\n".join(b["text"] for b in blocks)
    lines.append(f"3. ingest edited p85 {sync(store, embedder, edited)}")
    expected = len([c for p in edited for c in by_paragraph(p, STRATEGIES['B']['max_size'])])
    lines.append(f"   rows_in_db == chunks of edited corpus ({expected}): {store.count(NS) == expected}")

    with store._connect() as conn:
        conn.execute("DELETE FROM chunks WHERE strategy = %s", (NS,))
    lines.append(f"4. cleanup -> rows in '{NS}': {store.count(NS)}")
    text = "\n".join(lines)
    print(text)
    (RESULTS / "reingest_check.txt").write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
