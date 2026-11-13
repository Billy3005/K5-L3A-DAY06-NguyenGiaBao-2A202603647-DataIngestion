"""Build strategy A and B chunks, self-check them and export chunks + statistics.

Run from starter/:  python -m scripts.make_chunks
Outputs: results/chunks/{A,B}.jsonl, results/chunk_stats.csv
"""
import csv
import json
import re
import statistics
from dataclasses import asdict

from transformers import AutoTokenizer

from src.chunking import build_chunks
from src.config import EMBEDDING_MAX_TOKENS, EMBEDDING_MODEL, PAGES_JSONL, PASSAGE_PREFIX, RESULTS, STRATEGIES
from src.ingestion import read_pages_jsonl
from src.models import Chunk, DocumentPage


def build(name: str, pages: list[DocumentPage]) -> list[Chunk]:
    return build_chunks(pages, STRATEGIES[name])


def self_check(name: str, pages: list[DocumentPage], chunks: list[Chunk]) -> None:
    """Fail loudly if a chunk lost text, has wrong offsets or duplicate IDs."""
    by_page = {p.page: p for p in pages}
    assert len({c.chunk_id for c in chunks}) == len(chunks), f"{name}: duplicate chunk ids"
    for c in chunks:
        page = by_page[c.page]
        assert c.text == page.text[c.metadata["start_char"]:c.metadata["end_char"]], c.chunk_id
    for page in pages:   # every non-whitespace character of every page must be covered
        covered = bytearray(len(page.text))
        for c in (c for c in chunks if c.page == page.page):
            covered[c.metadata["start_char"]:c.metadata["end_char"]] = b"\x01" * len(c.text)
        lost = [ch for ch, cov in zip(page.text, covered) if not cov and not ch.isspace()]
        assert not lost, f"{name}: p{page.page} lost {len(lost)} chars"


def main() -> None:
    pages = read_pages_jsonl(PAGES_JSONL)
    tokenizer = AutoTokenizer.from_pretrained(EMBEDDING_MODEL)
    (RESULTS / "chunks").mkdir(parents=True, exist_ok=True)
    rows = []
    for name in ("A", "B"):
        chunks = build(name, pages)
        self_check(name, pages, chunks)
        tokens = [len(tokenizer(PASSAGE_PREFIX + c.text)["input_ids"]) for c in chunks]
        lengths = [len(c.text) for c in chunks]
        cut_mid_word = sum(1 for c in chunks if re.match(r"\w", c.text[:1]) and c.metadata["start_char"] > 0
                           and re.match(r"\w", next(p for p in pages if p.page == c.page)
                                        .text[c.metadata["start_char"] - 1]))
        with (RESULTS / "chunks" / f"{name}.jsonl").open("w", encoding="utf-8") as handle:
            for c, t in zip(chunks, tokens):
                handle.write(json.dumps({**asdict(c), "tokens": t}, ensure_ascii=False) + "\n")
        rows.append({
            "strategy": name, "params": json.dumps({k: v for k, v in STRATEGIES[name].items()
                                                     if k in ("chunking", "size", "overlap", "max_size")}),
            "chunks": len(chunks), "total_chars": sum(lengths),
            "len_min": min(lengths), "len_median": int(statistics.median(lengths)),
            "len_mean": round(statistics.mean(lengths)), "len_max": max(lengths),
            "tokens_total": sum(tokens), "tokens_max": max(tokens),
            "over_token_limit": sum(t > EMBEDDING_MAX_TOKENS for t in tokens),
            "starts_mid_word": cut_mid_word,
            "repaired_paragraph_splits": sum(c.metadata.get("repaired_splits", 0) for c in chunks),
        })
    with (RESULTS / "chunk_stats.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    for row in rows:
        print(row)
    print("Self-check OK: offsets exact, no lost text, unique ids. C reuses B's chunks.")


if __name__ == "__main__":
    main()
