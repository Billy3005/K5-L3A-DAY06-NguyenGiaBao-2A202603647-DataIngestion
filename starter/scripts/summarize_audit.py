"""Aggregate audit labels: LLM-assisted annotation with human verification. Never invents labels.

Labels (the only annotator):  LLM judge, in results/audit/{coherence_labels,metadata_audit,grounding_labels}.csv
Verification (the student):   results/audit/human_review.csv, one row per item with
                              llm_label, final_label, decision (accept | modify | audit_pass), reviewer_note

* final label = LLM label, except where the student's review modified it;
* the report shows BOTH the LLM labels (before review) and the final labels (after review);
* the review block lists acceptance per sheet and every modification. This is a review
  acceptance rate, NOT inter-annotator agreement (the reviewer saw the LLM labels).
Filter compliance comes from the traces (a fact, not a judgment).

Run from starter/:  python -m scripts.summarize_audit
Writes results/audit_summary.md and replaces the AUDIT_TABLE and REVIEW blocks in the report.
"""
import csv
import json
import re
import sys
from collections import Counter

from src.config import RESULTS, ROOT

AUDIT = RESULTS / "audit"
REPORT = ROOT / "report" / "individual" / "2A202603647_NguyenGiaBao.md"
VALID = {"coherence": {"0", "1", "2"}, "grounding": {"0", "1", "2"}, "metadata": {"Y", "N"}}
DECISIONS = {"accept", "modify", "audit_pass"}


def read(name):
    path = AUDIT / name
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def llm_labels() -> dict:
    labels = {}
    for r in read("coherence_labels.csv"):
        labels[("coherence", r["position"], r["strategy"])] = r["label_0_1_2"].strip()
    for r in read("metadata_audit.csv"):
        labels[("metadata", f"{r['id']}#{r['rank']}", r["strategy"])] = r["manual_all_correct_Y_N"].strip().upper()
    for r in read("grounding_labels.csv"):
        labels[("grounding", r["id"], r["strategy"])] = r["label_0_1_2"].strip()
    return labels


def norm(sheet: str, value: str) -> str:
    value = value.strip().upper() if sheet == "metadata" else value.strip()
    return value[0] if re.fullmatch(r"[012]\.0+", value) else value   # Excel re-saves 1 as "1.0"


def load_review(llm: dict, problems: list) -> tuple[dict, list]:
    final, rows = {}, read("human_review.csv")
    for r in rows:
        key = (r["sheet"], r["item"], r["strategy"])
        if key not in llm:
            problems.append(f"review row {key} does not exist in the LLM sheets")
            continue
        llm_value, final_value = norm(r["sheet"], r["llm_label"]), norm(r["sheet"], r["final_label"])
        decision = r["decision"].strip().lower()
        if llm_value != llm[key]:
            problems.append(f"{key}: review says LLM label {llm_value!r} but LLM sheet has {llm[key]!r}")
        if final_value not in VALID[r["sheet"]]:
            problems.append(f"{key}: invalid final_label {r['final_label']!r}")
            continue
        if decision not in DECISIONS:
            problems.append(f"{key}: decision must be one of {sorted(DECISIONS)}")
        if (decision == "modify") != (final_value != llm[key]):
            problems.append(f"{key}: decision {decision!r} inconsistent with labels {llm[key]!r} -> {final_value!r}")
        if decision == "modify" and not r["reviewer_note"].strip():
            problems.append(f"{key}: modification without reviewer_note")
        final[key] = final_value
    return final, rows


def scale_cell(labels: dict, sheet: str, strategy: str) -> str:
    source = "B" if (sheet == "coherence" and strategy == "C") else strategy
    vals = [int(v) for (s, _, st), v in labels.items() if s == sheet and st == source and v != ""]
    if not vals:
        return "PENDING"
    return f"{sum(vals) / len(vals):.2f}/2 ({'/'.join(str(vals.count(k)) for k in (0, 1, 2))})"


def meta_cell(labels: dict, strategy: str) -> str:
    vals = [v for (s, _, st), v in labels.items() if s == "metadata" and st == strategy and v != ""]
    return f"{vals.count('Y')}/{len(vals)}" if vals else "PENDING"


def inject(text: str, start: str, end: str, block: str) -> str:
    return re.sub(re.escape(start) + r".*?" + re.escape(end), f"{start}\n{block}\n{end}", text, flags=re.S)


def main() -> None:
    problems: list[str] = []
    llm = llm_labels()
    reviewed, rows = load_review(llm, problems)
    complete = len(reviewed) == len(llm) and not problems
    final = {k: reviewed.get(k, v) for k, v in llm.items()}

    traces = [json.loads(l) for l in (RESULTS / "traces" / "test.jsonl").open(encoding="utf-8")]
    table = ["| Strategy | Coherence /2 (0/1/2) | Metadata đủ và đúng (n/N) | Filter tuân thủ, test (n/N) | Grounding /2 (0/1/2): LLM → **sau kiểm duyệt** |",
             "|---|---|---|---|---|"]
    for strategy in ("A", "B", "C"):
        filt = [t for t in traces if t["strategy"] == strategy and t["question_filter"]]
        applied = any(t["filter_applied"] for t in filt)
        filt_txt = f"{sum(t['top3_in_filter_chapter'] for t in filt)}/{len(filt)}" + ("" if applied else " (không áp filter; chẩn đoán)")
        name = f"{strategy} (dùng chunk B)" if strategy == "C" else strategy
        g_before, g_after = scale_cell(llm, "grounding", strategy), scale_cell(final, "grounding", strategy)
        grounding = g_after if g_before == g_after else f"{g_before} → **{g_after}**"
        table.append(f"| {name} | {scale_cell(final, 'coherence', strategy)} | {meta_cell(final, strategy)} | {filt_txt} | {grounding} |")
    status = ("nhãn LLM judge **đã được học viên kiểm duyệt** (chấp nhận hoặc sửa từng mục)" if complete
              else f"nhãn LLM judge; kiểm duyệt của học viên mới có {len(reviewed)}/{len(llm)} mục")
    table_block = "\n".join(table) + f"\n\n_Nguồn: {status}. Sinh bởi `python -m scripts.summarize_audit` từ `starter/results/audit/`._"

    review_lines = ["| Phần | Mục đã kiểm duyệt | Chấp nhận nhãn LLM | Sửa |", "|---|---|---|---|"]
    mods = []
    for sheet in ("coherence", "metadata", "grounding"):
        keys = [k for k in reviewed if k[0] == sheet]
        changed = [k for k in keys if reviewed[k] != llm[k]]
        total = sum(1 for k in llm if k[0] == sheet)
        review_lines.append(f"| {sheet} | {len(keys)}/{total} | {len(keys) - len(changed)} | {len(changed)} |")
        mods += [f"{k[0]} {k[1]} {k[2]}: {llm[k]} → {reviewed[k]}" for k in changed]
    decisions = Counter(r["decision"].strip().lower() for r in rows)
    review_block = "\n".join(review_lines) + "\n\n" + (
        "Mục bị sửa: " + "; ".join(mods) + "." if mods else "Mục bị sửa: không có.") + (
        f" Quyết định ghi trong file: {dict(decisions)}." if rows else "") + (
        "\n\n_Đây là **tỷ lệ chấp nhận khi kiểm duyệt**, không phải độ đồng thuận giữa hai người chấm độc lập: "
        "người kiểm duyệt đã thấy nhãn và lý do của LLM._")

    (RESULTS / "audit_summary.md").write_text(table_block + "\n\n" + review_block + "\n", encoding="utf-8")
    if REPORT.exists():
        text = REPORT.read_text(encoding="utf-8")
        text = inject(text, "<!-- AUDIT_TABLE_START -->", "<!-- AUDIT_TABLE_END -->", table_block)
        text = inject(text, "<!-- REVIEW_START -->", "<!-- REVIEW_END -->", review_block)
        REPORT.write_text(text, encoding="utf-8")
    print(table_block, "\n\n", review_block, sep="")
    for p in problems:
        print("PROBLEM", p)
    if problems:
        sys.exit(f"{len(problems)} problem(s) in the review sheet.")
    print("Review complete." if complete else "Review incomplete.")


if __name__ == "__main__":
    main()
