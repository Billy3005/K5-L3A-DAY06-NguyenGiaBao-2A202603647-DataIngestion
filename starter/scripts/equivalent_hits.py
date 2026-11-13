"""Secondary metric: Hit@1 / Hit@3 that also accepts grader-confirmed EQUIVALENT evidence.

GUIDE.md: a hit is a chunk on a gold page containing the recorded evidence "or equivalent
evidence confirmed by the grader". The primary, pre-registered metric (src/evaluation.py)
uses only the recorded quotes. This script recomputes from the saved traces, adding the
quotes in results/audit/equivalent_evidence.jsonl that the student confirmed
(confirmed_by_student == "yes"). Those quotes were added AFTER results were seen, so this
is a secondary, clearly labeled metric - it never replaces the primary one.

Run from starter/:  python -m scripts.equivalent_hits
Output: results/metrics_equivalent.csv (+ table injected into the report)
"""
import csv
import json
import re
from collections import defaultdict

from src.config import RESULTS, ROOT
from src.ingestion import match_key

EQUIV = RESULTS / "audit" / "equivalent_evidence.jsonl"   # kept out of the frozen benchmark/ folder
REPORT = ROOT / "report" / "individual" / "2A202603647_NguyenGiaBao.md"
START, END = "<!-- EQUIV_TABLE_START -->", "<!-- EQUIV_TABLE_END -->"


def main() -> None:
    entries = [json.loads(l) for l in EQUIV.open(encoding="utf-8") if l.strip()]
    confirmed = [e for e in entries if str(e.get("confirmed_by_student", "")).strip().lower() == "yes"]
    pending = [e["id"] for e in entries if e not in confirmed]
    extra = defaultdict(list)
    for e in confirmed:
        extra[e["id"]].append((e["gold_page"], match_key(e["evidence_quote"])))

    rows, changed = [], []
    for split in ("dev", "test"):
        traces = [json.loads(l) for l in (RESULTS / "traces" / f"{split}.jsonl").open(encoding="utf-8")]
        agg = defaultdict(lambda: {"N": 0, "h1": 0, "h3": 0, "h1e": 0, "h3e": 0})
        for t in traces:
            first = None
            for h in t["hits"]:
                eq = any(h["page"] == p and quote in match_key(h["text"]) for p, quote in extra.get(t["id"], []))
                if h["is_hit"] or eq:
                    first = first or h["rank"]
                    if eq and not h["is_hit"]:
                        changed.append(f"{split} {t['id']} {t['strategy']} rank {h['rank']} p{h['page']}")
            a = agg[t["strategy"]]
            a["N"] += 1
            a["h1"] += t["hit1"]
            a["h3"] += t["hit3"]
            a["h1e"] += first == 1
            a["h3e"] += first is not None
        for strategy, a in sorted(agg.items()):
            rows.append({"split": split, "strategy": strategy, "N": a["N"],
                         "hit1_strict": f"{a['h1']}/{a['N']}", "hit3_strict": f"{a['h3']}/{a['N']}",
                         "hit1_with_equivalent": f"{a['h1e']}/{a['N']}", "hit3_with_equivalent": f"{a['h3e']}/{a['N']}"})
    with (RESULTS / "metrics_equivalent.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    lines = ["| Split | Strategy | Hit@1 chặt | Hit@3 chặt | Hit@1 + tương đương | Hit@3 + tương đương |",
             "|---|---|---|---|---|---|"]
    lines += [f"| {r['split']} | {r['strategy']} | {r['hit1_strict']} | {r['hit3_strict']} | "
              f"{r['hit1_with_equivalent']} | {r['hit3_with_equivalent']} |" for r in rows]
    status = (f"Bằng chứng tương đương đã được học viên xác nhận: {[e['id'] for e in confirmed] or 'chưa có'}"
              + (f"; **chờ học viên xác nhận: {pending}** (cột tương đương hiện bằng cột chặt)" if pending else "")
              + f". Các ô thay đổi: {changed or 'không có'}.")
    block = "\n".join(lines) + "\n\n_" + status + " Sinh bởi `python -m scripts.equivalent_hits`._"
    if REPORT.exists():
        text = REPORT.read_text(encoding="utf-8")
        if START in text:
            text = re.sub(re.escape(START) + r".*?" + re.escape(END), f"{START}\n{block}\n{END}", text, flags=re.S)
            REPORT.write_text(text, encoding="utf-8")
    print(block)


if __name__ == "__main__":
    main()
