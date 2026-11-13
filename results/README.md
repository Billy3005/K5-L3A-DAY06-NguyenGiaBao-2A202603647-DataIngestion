# results/

SUBMISSION.md expects a top-level `results/` folder. In this repo, all results live next to the code that produces them, in **[`starter/results/`](../starter/results/)**, so the paths written by the scripts and the report links stay consistent.

| What | Where |
|---|---|
| Full top-3 traces (dev, test, post-hoc ablation) | [`starter/results/traces/`](../starter/results/traces/) |
| Hit@1 / Evidence Hit@3 (n/N) | `starter/results/metrics_dev.csv`, `metrics_test.csv`, `metrics_equivalent.csv`, `metrics_ablation_dev.csv` |
| Strategy choice made on dev before test | [`starter/results/selection.json`](../starter/results/selection.json) |
| Chunk statistics, ingest log, re-ingest checks | `starter/results/chunk_stats.csv`, `ingest_log.csv`, `ingest_runs.csv`, `reingest_check.txt` |
| Manual audit (LLM judge + student labels, agreement) | [`starter/results/audit/`](../starter/results/audit/), `starter/results/audit_summary.md` |
| Description of every file and the extraction log | [`starter/results/README.md`](../starter/results/README.md) |
