"""Pipeline entry point.

  python -m src.run ingest                 # chunk + embed + upsert indexes A and B (idempotent)
  python -m src.run query --strategy C --chapter 4 "your question"
  python -m src.run evaluate --split dev   # traces + metrics for A, B, C
  python -m src.run select                 # apply pre-registered dev criteria -> results/selection.json
  python -m src.run evaluate --split test  # refused until selection.json exists

Strategies are defined in src/config.py. C reuses index B and only adds a filter.
"""
import argparse
import csv
import json
import os
import platform
import time
from datetime import datetime, timezone

from dotenv import load_dotenv

from .chunking import build_chunks
from .config import (ABLATIONS, ALL_CONFIGS, EMBEDDING_DIM, PAGES_JSONL, QUESTIONS, RESULTS, STARTER,
                     STRATEGIES, TOP_K)
from .embeddings import E5Embedder
from .evaluation import evaluate_query, summarize
from .ingestion import read_pages_jsonl
from .store import PgVectorStore, content_hash

INGEST_LOG = RESULTS / "ingest_runs.csv"
SELECTION = RESULTS / "selection.json"


def get_store() -> PgVectorStore:
    load_dotenv(STARTER / ".env")
    store = PgVectorStore(os.getenv("DATABASE_URL", ""), EMBEDDING_DIM)
    store.create_schema()
    return store


def ingest(store: PgVectorStore, embedder: E5Embedder, index: str) -> dict:
    """Chunk the corpus for `index`, embed only new/changed chunks, sync to pgvector."""
    cfg = next(c for c in ALL_CONFIGS.values() if c["index"] == index)
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
    cfg = ALL_CONFIGS[strategy]
    applied = question_filter if (cfg["use_filter"] and question_filter) else None
    return store.search(cfg["index"], embedder.embed_query(question), TOP_K, applied), applied


def evaluate(store: PgVectorStore, embedder: E5Embedder, split: str, configs: dict | None = None,
             tag: str = "") -> list[dict]:
    """Run every strategy on one split; save full top-3 traces and n/N metrics."""
    configs = configs or STRATEGIES
    if split == "test" and not SELECTION.exists():
        raise SystemExit("Refusing to run test: choose the strategy on dev first (python -m src.run select).")
    if split == "test" and any(name in ABLATIONS for name in configs):
        raise SystemExit("Refusing to run post-hoc ablations on test: the test split is already spent.")
    questions = [json.loads(l) for l in QUESTIONS.open(encoding="utf-8") if l.strip()]
    questions = [q for q in questions if q["split"] == split]
    traces = []
    for q in questions:
        query_vector = embedder.embed_query(q["question"])   # same query vector for A, B and C
        for strategy, cfg in configs.items():
            applied = q["filter"] if (cfg["use_filter"] and q["filter"]) else None
            t0 = time.perf_counter()
            hits = store.search(cfg["index"], query_vector, TOP_K, applied)
            search_ms = (time.perf_counter() - t0) * 1000
            traces.append({"strategy": strategy, "index": cfg["index"], "split": split, "id": q["id"],
                           "type": q["type"], "question": q["question"], "question_filter": q["filter"],
                           "filter_applied": applied, "gold_source_id": q["gold_source_id"],
                           "gold_page": q["gold_page"], "evidence_quote": q["evidence_quote"],
                           "alt_gold": q.get("alt_gold", []), "expected_answer": q["expected_answer"],
                           "search_ms": round(search_ms, 2), "model": embedder.model_name,
                           **evaluate_query(q, hits)})
    (RESULTS / "traces").mkdir(exist_ok=True)
    with (RESULTS / "traces" / f"{tag}{split}.jsonl").open("w", encoding="utf-8") as handle:
        for t in traces:
            handle.write(json.dumps(t, ensure_ascii=False) + "\n")
    rows = summarize(traces)
    with (RESULTS / f"metrics_{tag}{split}.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return rows


def select_strategy() -> dict:
    """Apply the pre-registered dev-only criteria (benchmark/README.md) and record the choice."""
    rows = list(csv.DictReader((RESULTS / "metrics_dev.csv").open(encoding="utf-8")))
    overall = {r["strategy"]: r for r in rows if r["subset"] == "all"}
    filt = {r["strategy"]: r for r in rows if r["subset"] == "filter_questions"}
    chunk_counts = {r["strategy"]: int(r["chunks"]) for r in csv.DictReader((RESULTS / "chunk_stats.csv").open())}
    chunk_counts["C"] = chunk_counts["B"]
    log = []
    candidates = sorted(overall)
    best = max(int(overall[s]["hit3"]) for s in candidates)
    candidates = [s for s in candidates if best - int(overall[s]["hit3"]) <= 1]
    log.append(f"1. dev Hit@3 {[(s, overall[s]['hit3_frac']) for s in sorted(overall)]} -> within 1 of best: {candidates}")
    if len(candidates) > 1:
        best1 = max(int(overall[s]["hit1"]) for s in candidates)
        candidates = [s for s in candidates if best1 - int(overall[s]["hit1"]) <= 1]
        log.append(f"2. dev Hit@1 {[(s, overall[s]['hit1_frac']) for s in candidates]} -> {candidates}")
    if len(candidates) > 1:
        fewest = min(chunk_counts[s] for s in candidates)
        candidates = [s for s in candidates if chunk_counts[s] == fewest]
        log.append(f"3. fewest chunks -> {candidates}")
    if set(candidates) == {"B", "C"}:
        c_ok = int(filt["C"]["hit3"]) >= int(filt["B"]["hit3"])
        candidates = ["C"] if c_ok else ["B"]
        log.append(f"4. C vs B on dev filter questions: C {filt['C']['hit3_frac']} vs B {filt['B']['hit3_frac']} -> {candidates}")
    choice = {"chosen": candidates[0], "decided_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "based_on": "dev only (test not run yet)", "steps": log}
    SELECTION.write_text(json.dumps(choice, indent=2), encoding="utf-8")
    return choice


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    ing = sub.add_parser("ingest")
    ing.add_argument("--index", action="append", choices=sorted({c["index"] for c in ALL_CONFIGS.values()}),
                     help="default: A and B (the pre-registered indexes)")
    q = sub.add_parser("query")
    q.add_argument("question")
    q.add_argument("--strategy", choices=sorted(ALL_CONFIGS), default="B")
    q.add_argument("--chapter", type=int)
    e = sub.add_parser("evaluate")
    e.add_argument("--split", choices=["dev", "test"], required=True)
    e.add_argument("--ablation", action="store_true",
                   help="post-hoc: evaluate A, B and the ablation configs (dev only) into *_ablation_* files")
    sub.add_parser("select")
    args = parser.parse_args()

    if args.cmd == "select":
        print(json.dumps(select_strategy(), indent=2))
        return
    store, embedder = get_store(), E5Embedder()
    if args.cmd == "evaluate":
        configs, tag = None, ""
        if args.ablation:
            configs, tag = {"A": STRATEGIES["A"], "B": STRATEGIES["B"], **ABLATIONS}, "ablation_"
        for row in evaluate(store, embedder, args.split, configs, tag):
            if row["subset"] in ("all", "filter_questions"):
                print(f"{row['strategy']} {row['split']:<4} {row['subset']:<17} Hit@1 {row['hit1_frac']:<6} "
                      f"Hit@3 {row['hit3_frac']:<6} gold-page@3 {row['gold_page_in_top3']:<6} "
                      f"split-evidence misses {row['evidence_split_misses']}  filter-chapter top3 "
                      f"{row['top3_in_filter_chapter']}  {row['mean_query_ms']} ms")
    elif args.cmd == "ingest":
        for index in (args.index or ["A", "B"]):
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
