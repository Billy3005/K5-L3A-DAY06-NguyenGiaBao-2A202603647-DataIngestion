"""Automatic retrieval metrics (Hit@1, Evidence Hit@3) and full per-query traces.

Definition (pre-registered in benchmark/README.md): a retrieved chunk is a HIT when
its document + page equal a gold page (primary or alt_gold) AND the normalized
evidence quote for that page is a substring of the normalized chunk text.
Human labels (coherence, grounding, metadata correctness) are NOT inferred here;
see scripts/make_audit_sheets.py, which only prepares sheets for manual scoring.
"""
from collections import defaultdict
from typing import Any

from .ingestion import match_key


def _golds(question: dict[str, Any]) -> list[tuple[int, str]]:
    return [(question["gold_page"], question["evidence_quote"])] + \
           [(g["gold_page"], g["evidence_quote"]) for g in question.get("alt_gold", [])]


def _partial(evidence: str, text: str) -> bool:
    """Evidence cut by a chunk boundary: its first or last third appears, but not all of it."""
    words = match_key(evidence).split()
    third = max(3, len(words) // 3)
    return " ".join(words[:third]) in text or " ".join(words[-third:]) in text


def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    golds = _golds(question)
    gold_pages = {p for p, _ in golds}
    ranked = []
    for rank, h in enumerate(hits, 1):
        text = match_key(h["text"])
        same_doc = h["document_id"] == question["gold_source_id"]
        is_hit = same_doc and any(h["page"] == p and match_key(e) in text for p, e in golds)
        page_match = same_doc and h["page"] in gold_pages
        ranked.append({
            "rank": rank, "chunk_id": h["chunk_id"], "document_id": h["document_id"], "source": h["source"],
            "page": h["page"], "chapter": h["chapter"], "section": h["section"],
            "start_char": h["start_char"], "end_char": h["end_char"], "score": round(float(h["score"]), 6),
            "is_hit": is_hit, "gold_page_match": page_match,
            "partial_evidence": page_match and not is_hit and any(
                h["page"] == p and _partial(e, text) for p, e in golds),
            "text": h["text"],
        })
    first = next((r["rank"] for r in ranked if r["is_hit"]), None)
    wanted = (question.get("filter") or {}).get("chapter")
    return {
        "hit1": first == 1, "hit3": first is not None, "first_hit_rank": first,
        "gold_page_in_top3": any(r["gold_page_match"] for r in ranked),
        "evidence_split_in_top3": first is None and any(r["partial_evidence"] for r in ranked),
        # For questions with a filter: do all top-3 results lie in the requested chapter?
        "top3_in_filter_chapter": None if wanted is None else all(r["chapter"] == wanted for r in ranked),
        "hits": ranked,
    }


def summarize(traces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Hit@1 / Evidence Hit@3 as n/N per strategy x split, plus per-subset breakdowns."""
    groups: dict[tuple, list] = defaultdict(list)
    for t in traces:
        groups[(t["strategy"], t["split"], "all")].append(t)
        groups[(t["strategy"], t["split"], f"type={t['type']}")].append(t)
        if t["question_filter"]:
            groups[(t["strategy"], t["split"], "filter_questions")].append(t)
    rows = []
    for (strategy, split, subset), items in sorted(groups.items()):
        n = len(items)
        h1 = sum(t["hit1"] for t in items)
        h3 = sum(t["hit3"] for t in items)
        filt = [t for t in items if t["top3_in_filter_chapter"] is not None]
        rows.append({
            "strategy": strategy, "split": split, "subset": subset, "N": n,
            "hit1": h1, "hit1_frac": f"{h1}/{n}", "hit1_pct": round(100 * h1 / n, 1),
            "hit3": h3, "hit3_frac": f"{h3}/{n}", "hit3_pct": round(100 * h3 / n, 1),
            "gold_page_in_top3": f"{sum(t['gold_page_in_top3'] for t in items)}/{n}",
            "evidence_split_misses": sum(t["evidence_split_in_top3"] for t in items),
            "top3_in_filter_chapter": f"{sum(t['top3_in_filter_chapter'] for t in filt)}/{len(filt)}" if filt else "N/A",
            "mean_query_ms": round(sum(t["search_ms"] for t in items) / n, 1),
        })
    return rows
