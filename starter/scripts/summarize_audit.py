"""Aggregate the author's manual labels into the report tables. Never invents labels.

Reads results/audit/{coherence_labels,metadata_audit,grounding_labels}.csv (filled by
hand), validates them, and writes results/audit_summary.md. It also replaces the block
between <!-- AUDIT_TABLE_START --> and <!-- AUDIT_TABLE_END --> in the report.
Unlabeled items are reported as PENDING, never as a default score.
Filter compliance is computed from the traces (a fact, not a judgment).

Run from starter/:  python -m scripts.summarize_audit
"""
import csv
import json
import re
import sys

from src.config import RESULTS, ROOT

AUDIT = RESULTS / "audit"
REPORT = ROOT / "report" / "individual" / "2A202603647_NguyenGiaBao.md"
START, END = "<!-- AUDIT_TABLE_START -->", "<!-- AUDIT_TABLE_END -->"


def read(name):
    with (AUDIT / name).open(encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def labels(rows, strategy_rows, problems, sheet):
    vals = []
    for r in strategy_rows:
        raw = r["label_0_1_2"].strip()
        if raw == "":
            continue
        if raw not in {"0", "1", "2"}:
            problems.append(f"{sheet}: invalid label {raw!r} ({r.get('position') or r.get('id')} {r['strategy']})")
            continue
        if not r["reason"].strip():
            problems.append(f"{sheet}: label without reason ({r.get('position') or r.get('id')} {r['strategy']})")
        vals.append(int(raw))
    return vals


def fmt_scale(vals, total):
    if not vals:
        return f"PENDING (0/{total} labeled)"
    dist = "/".join(str(vals.count(k)) for k in (0, 1, 2))
    mean = sum(vals) / len(vals)
    suffix = "" if len(vals) == total else f", PARTIAL {len(vals)}/{total}"
    return f"{mean:.2f}/2 (n={len(vals)}; 0/1/2 = {dist}{suffix})"


def main() -> None:
    problems = []
    coherence, metadata, grounding = read("coherence_labels.csv"), read("metadata_audit.csv"), read("grounding_labels.csv")
    traces = [json.loads(l) for l in (RESULTS / "traces" / "test.jsonl").open(encoding="utf-8")]
    rows = []
    for strategy in ("A", "B", "C"):
        coh_rows = [r for r in coherence if r["strategy"] == ("A" if strategy == "A" else "B")]
        coh = labels(coherence, coh_rows, problems, "coherence")
        meta_rows = [r for r in metadata if r["strategy"] == strategy]
        meta_done = [r for r in meta_rows if r["manual_all_correct_Y_N"].strip()]
        meta_bad = [r for r in meta_done if r["manual_all_correct_Y_N"].strip().upper() not in {"Y", "N"}]
        problems += [f"metadata: invalid Y/N {r['manual_all_correct_Y_N']!r} ({r['id']} {strategy} #{r['rank']})" for r in meta_bad]
        meta_y = sum(r["manual_all_correct_Y_N"].strip().upper() == "Y" for r in meta_done)
        meta = (f"{meta_y}/{len(meta_done)}" + ("" if len(meta_done) == len(meta_rows) else f" (PARTIAL, {len(meta_rows)} records)")) \
            if meta_done else f"PENDING (0/{len(meta_rows)} checked)"
        filt = [t for t in traces if t["strategy"] == strategy and t["question_filter"]]
        comply = sum(t["top3_in_filter_chapter"] for t in filt)
        applied = any(t["filter_applied"] for t in filt)
        filt_txt = f"{comply}/{len(filt)}" + ("" if applied else " (filter not applied; diagnostic)")
        gro = labels(grounding, [r for r in grounding if r["strategy"] == strategy], problems, "grounding")
        rows.append({"strategy": strategy, "coherence": fmt_scale(coh, len(coh_rows)), "metadata": meta,
                     "filter": filt_txt, "grounding": fmt_scale(gro, 6)})

    table = ["| Strategy | Coherence trung bình /2 (n) | Metadata đủ và đúng (n/N) | Filter tuân thủ, test (n/N) | Grounding 0/1/2 và trung bình /2 |",
             "|---|---|---|---|---|"]
    table += [f"| {r['strategy']}{' (dùng chunk B)' if r['strategy'] == 'C' else ''} | {r['coherence']} | {r['metadata']} | {r['filter']} | {r['grounding']} |"
              for r in rows]
    block = "\n".join(table) + ("\n\n_Bảng do `python -m scripts.summarize_audit` sinh từ nhãn trong "
                                "`starter/results/audit/` (người chấm và phương pháp: xem mục ngay dưới)._")
    (RESULTS / "audit_summary.md").write_text(block + "\n", encoding="utf-8")
    if REPORT.exists():
        text = REPORT.read_text(encoding="utf-8")
        text = re.sub(re.escape(START) + r".*?" + re.escape(END), f"{START}\n{block}\n{END}", text, flags=re.S)
        REPORT.write_text(text, encoding="utf-8")
    print(block)
    for p in problems:
        print("PROBLEM", p)
    pending = sum("PENDING" in v or "PARTIAL" in v for r in rows for v in r.values())
    if problems:
        sys.exit(f"{len(problems)} labeling problem(s) to fix.")
    print("All labels complete." if not pending else f"{pending} cell(s) still pending manual labels.")


if __name__ == "__main__":
    main()
