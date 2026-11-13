"""Verify benchmark/questions.jsonl against the normalized corpus BEFORE any retrieval run.

Checks (fails loudly on any error):
  * required fields, unique ids, split sizes (>=15 dev, >=5 test), >=3 filter questions with >=1 in test
  * every evidence_quote (primary and alt_gold) occurs on its gold page after normalization
  * filter values exist in the corpus metadata and match the gold page (filter must not exclude the gold)
  * the question does not leak the evidence (no 8-word overlap between question and evidence)
Informational: evidence that also occurs on other pages, evidence crossing a paragraph-block boundary.

Run from starter/:  python -m scripts.verify_benchmark
"""
import json
import sys
from pathlib import Path

from src.ingestion import match_key

STARTER = Path(__file__).resolve().parents[1]
QUESTIONS = STARTER.parent / "benchmark" / "questions.jsonl"
PAGES = STARTER / "data" / "processed" / "pages.jsonl"
REQUIRED = ["id", "split", "type", "question", "expected_answer", "gold_source_id",
            "gold_page", "evidence_quote", "filter"]


def ngrams(text: str, n: int = 8) -> set[tuple[str, ...]]:
    words = match_key(text).split()
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def main() -> None:
    pages = {r["page"]: r for r in map(json.loads, PAGES.open(encoding="utf-8"))}
    keys = {p: match_key(r["text"]) for p, r in pages.items()}
    chapters = {r["chapter"] for r in pages.values()}
    questions = [json.loads(line) for line in QUESTIONS.open(encoding="utf-8") if line.strip()]
    errors, notes = [], []

    ids = [q.get("id") for q in questions]
    if len(set(ids)) != len(ids):
        errors.append("duplicate ids")
    for q in questions:
        missing = [f for f in REQUIRED if f not in q]
        if missing:
            errors.append(f"{q.get('id')}: missing {missing}")
            continue
        golds = [{"gold_page": q["gold_page"], "evidence_quote": q["evidence_quote"]}] + q.get("alt_gold", [])
        for gold in golds:
            page, quote = gold["gold_page"], match_key(gold["evidence_quote"])
            if page not in keys:
                errors.append(f"{q['id']}: gold page {page} not in corpus")
                continue
            if quote not in keys[page]:
                errors.append(f"{q['id']}: evidence NOT found on p{page}: {gold['evidence_quote'][:70]}")
                continue
            elsewhere = [p for p, text in keys.items() if p != page and quote in text]
            if elsewhere:
                notes.append(f"{q['id']}: evidence also on pages {elsewhere}")
            if not any(quote in match_key(b["text"]) for b in pages[page]["blocks"]):
                notes.append(f"{q['id']}: evidence on p{page} spans a paragraph-block boundary")
        if q["filter"]:
            chapter = q["filter"].get("chapter")
            if chapter not in chapters:
                errors.append(f"{q['id']}: filter chapter {chapter} does not exist in corpus")
            for gold in golds:
                if pages.get(gold["gold_page"], {}).get("chapter") != chapter:
                    errors.append(f"{q['id']}: filter excludes gold page {gold['gold_page']}")
        if ngrams(q["question"]) & ngrams(q["evidence_quote"]):
            errors.append(f"{q['id']}: question shares an 8-word span with its evidence (leak)")

    dev = [q for q in questions if q["split"] == "dev"]
    test = [q for q in questions if q["split"] == "test"]
    filt = [q for q in questions if q.get("filter")]
    filt_test = [q for q in filt if q["split"] == "test"]
    if len(dev) < 15 or len(test) < 5:
        errors.append(f"split sizes dev={len(dev)} test={len(test)} (need >=15/>=5)")
    if len(filt) < 3 or not filt_test:
        errors.append(f"filter questions total={len(filt)} test={len(filt_test)} (need >=3, >=1 test)")
    dev_sections = {q["section"] for q in dev}
    overlap = sorted({q["section"] for q in test} & dev_sections)

    types = {}
    for q in questions:
        types.setdefault((q["split"], q["type"]), 0)
        types[(q["split"], q["type"])] += 1
    print(f"questions={len(questions)} dev={len(dev)} test={len(test)} "
          f"filter={len(filt)} (test {len(filt_test)})")
    print("by split/type:", dict(sorted(types.items())))
    print("test sections overlapping dev sections:", overlap or "none")
    for note in notes:
        print("NOTE", note)
    for error in errors:
        print("ERROR", error)
    if errors:
        sys.exit(f"{len(errors)} error(s): fix the benchmark before running any strategy.")
    print("Benchmark OK: all evidence verified on gold pages.")


if __name__ == "__main__":
    main()
