"""Prepare manual-audit sheets. This script NEVER fills human labels.

Outputs in results/audit/:
  coherence_labels.csv  10 pre-registered positions x strategies A, B (C uses B's chunks)
  metadata_audit.csv    6 test questions x top-3 x A/B/C; machine pre-checks + empty manual columns
  grounding_labels.csv  6 test questions x A/B/C; top-3 evidence shown, empty 0/1/2 label
  REVIEW.md             the same items in readable form for labeling
Run from starter/:  python -m scripts.make_audit_sheets
"""
import csv
import json

from src.config import PAGES_JSONL, RESULTS
from src.ingestion import match_key

AUDIT = RESULTS / "audit"
COHERENCE_PAGES = [59, 67, 75, 83, 98, 106, 114, 341, 349, 357]   # pre-registered in benchmark/README.md


def load_jsonl(path):
    return [json.loads(l) for l in path.open(encoding="utf-8") if l.strip()]


def sentence_at(text: str, offset: int) -> str:
    start = max(text.rfind(". ", 0, offset), text.rfind("\n", 0, offset)) + 1
    end = min([i for i in (text.find(". ", offset), text.find("\n", offset)) if i != -1] or [len(text)])
    return text[start:end + 1].strip()


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as handle:   # BOM: opens cleanly in Excel
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    AUDIT.mkdir(exist_ok=True)
    pages = {p["page"]: p for p in load_jsonl(PAGES_JSONL)}
    chunks = {s: load_jsonl(RESULTS / "chunks" / f"{s}.jsonl") for s in ("A", "B")}
    traces = load_jsonl(RESULTS / "traces" / "test.jsonl")
    md = ["# Manual audit — review sheet",
          "Fill labels in the CSV files (not here). Scorer: the author (risk of bias noted in report).", ""]

    # 1. Coherence -----------------------------------------------------------
    rows, md_part = [], ["## 1. Chunk coherence (0 = cut mid-idea/unintelligible, 1 = partly understandable/missing context, 2 = self-contained, complete idea)", ""]
    for n, page in enumerate(COHERENCE_PAGES, 1):
        text = pages[page]["text"]
        offset = len(text) // 2
        md_part += [f"### Position P{n:02d}: page {page}, offset {offset}",
                    f"Sentence at position: _{sentence_at(text, offset)}_", ""]
        for strategy in ("A", "B"):
            covering = [c for c in chunks[strategy] if c["page"] == page
                        and c["metadata"]["start_char"] <= offset < c["metadata"]["end_char"]]
            chunk = covering[0]   # rule: first chunk (lowest start) covering the offset
            rows.append({"position": f"P{n:02d}", "page": page, "offset": offset, "strategy": strategy,
                         "applies_to": "A" if strategy == "A" else "B and C",
                         "chunk_id": chunk["chunk_id"], "covering_chunks": len(covering),
                         "chunk_chars": len(chunk["text"]), "chunk_text": chunk["text"],
                         "label_0_1_2": "", "reason": ""})
            md_part += [f"**{strategy}** `{chunk['chunk_id']}` ({len(chunk['text'])} chars)", "", "```text",
                        chunk["text"], "```", ""]
    write_csv(AUDIT / "coherence_labels.csv", rows)
    md += md_part

    # 2. Metadata ------------------------------------------------------------
    rows, md_part = [], ["## 2. Metadata (verify source/page/chapter/section against the PDF page)", ""]
    for t in traces:
        for h in t["hits"]:
            page = pages[h["page"]]
            rows.append({
                "strategy": t["strategy"], "id": t["id"], "rank": h["rank"], "chunk_id": h["chunk_id"],
                "source": h["source"], "page": h["page"], "chapter": h["chapter"], "section": h["section"],
                "question_filter": json.dumps(t["question_filter"]) if t["question_filter"] else "",
                "filter_applied": json.dumps(t["filter_applied"]) if t["filter_applied"] else "",
                "auto_text_found_on_page": match_key(h["text"]) in match_key(page["text"]),
                "auto_chapter_matches_manifest": h["chapter"] == page["chapter"],
                "auto_section_in_page_sections": h["section"] in page["sections"],
                "manual_source_ok": "", "manual_page_ok": "", "manual_chapter_ok": "",
                "manual_section_ok": "", "manual_all_correct_Y_N": "", "notes": ""})
    write_csv(AUDIT / "metadata_audit.csv", rows)
    md_part.append(f"{len(rows)} records in metadata_audit.csv (open PDF at the listed physical page to verify).")
    md += md_part + [""]

    # 3. Grounding -----------------------------------------------------------
    rows, md_part = [], ["## 3. Grounding (0 = no evidence, 1 = evidence present but missing condition/context, 2 = enough to answer and trace the source)", ""]
    for t in traces:
        top3 = "\n\n".join(f"[#{h['rank']} p{h['page']} ch{h['chapter']} {h['chunk_id']}]\n{h['text']}" for h in t["hits"])
        rows.append({"strategy": t["strategy"], "id": t["id"], "type": t["type"], "question": t["question"],
                     "filter_applied": json.dumps(t["filter_applied"]) if t["filter_applied"] else "",
                     "expected_answer": t["expected_answer"], "gold_page": t["gold_page"],
                     "evidence_quote": t["evidence_quote"], "auto_evidence_hit3_proxy": t["hit3"],
                     "top3_text": top3, "label_0_1_2": "", "reason": ""})
        md_part += [f"### {t['id']} — strategy {t['strategy']} (filter applied: {t['filter_applied']})",
                    f"**Q:** {t['question']}  ", f"**Expected:** {t['expected_answer']}  ",
                    f"**Gold:** p{t['gold_page']} — _{t['evidence_quote']}_", "", "```text", top3, "```", ""]
    write_csv(AUDIT / "grounding_labels.csv", rows)
    md += md_part
    (AUDIT / "REVIEW.md").write_text("\n".join(md), encoding="utf-8")
    print("Wrote coherence_labels.csv (20 rows), metadata_audit.csv, grounding_labels.csv, REVIEW.md")


if __name__ == "__main__":
    main()
