# Benchmark — Principles of Microeconomics 3e (Ch3, Ch4, Ch14)

Frozen **before any retrieval run**. Verified with `python -m scripts.verify_benchmark` (from `starter/`).
Any later change to this folder must be recorded in the report and the affected split must not be treated as an independent holdout.

## Files

| File | Content |
|---|---|
| `questions.jsonl` | 22 questions: `id, split, type, section, question, expected_answer, gold_source_id, gold_page, evidence_quote, alt_gold, filter` |

`gold_page` is the **physical PDF page (1-based)** of `principles-microeconomics-3e_-_WEB.pdf`, not the printed page number (printed = physical − 12 in these chapters). `alt_gold` lists other pages whose evidence is equally valid; a hit on any of them counts.

## Design

- **Language: English**, the same as the corpus. Questions, evidence and corpus share one language, so the A/B/C comparison measures chunking and metadata only and is not mixed with cross-lingual retrieval error.
- **Split rule (by section, fixed before running):** test questions come only from sections **3.4, 4.2, 14.3, 14.5**, and none of those sections is used by any dev question. This reduces leakage from tuning on dev questions about the same passage. The verify script checks that the overlap is empty.
- **Split:** 16 dev / 6 test.

| Split | direct | paraphrase | conditional | filter | Total |
|---|---:|---:|---:|---:|---:|
| dev | 5 | 4 | 4 | 3 | 16 |
| test | 2 | 1 | 1 | 2 | 6 |

- **Evidence:** the minimal sentence(s) that support the answer, including its condition when there is one. Each quote is copied from the normalized text (`starter/data/processed/pages.jsonl`) and machine-checked on the gold page. Paraphrase questions deliberately avoid the source wording; an automatic 8-word-overlap check guards against leaking the evidence into the query.

## Metadata filter questions (q05, q09, q13, q18, q19)

The filter is `{"chapter": N}`. It is an **assumed input supplied before retrieval**: the learner is currently studying chapter N, and the app passes that scope. The filter is never derived from the gold page at query time. Chapter values come from the PDF's own outline (`data/manifest_pages.csv`).

Each filter question is deliberately ambiguous **across** chapters. The distractors below were noted while reading the source, before any run:

| id | Filter | Gold | Expected cross-chapter distractor |
|---|---|---|---|
| q05 | ch3 | p76, generic Step 2 | ch4 p102–103: Step 2 of the technology/wages example |
| q09 | ch4 | p104, living wage → surplus of labor | ch3 p85–86: wheat price floor → surplus |
| q13 | ch14 | p339, derived demand via MPL × P | ch4 p100–101: derived demand and shift factors |
| q18 | ch3 | p85, wheat price support → surplus | ch4 p104: living wage price floor |
| q19 | ch4 | p111, credit-card ceiling → credit shortage | ch3 p83–84: rent control → housing shortage |

Strategy C applies the filter only to these 5 questions. For every other question, C runs **without** a filter, so C equals B there by construction.

**Known risk:** the author wrote the questions knowing the gold pages, so wording may unconsciously favour retrieval. Filter questions with the same concept appear in both dev (q09) and test (q18), with different wording and a different chapter. This is a mild leakage risk that will be reported.

## Metric definitions (fixed now)

- **Hit for one retrieved chunk:** chunk `source_id` + `page` equals a gold page (primary or `alt_gold`), **and** the normalized evidence quote is a substring of the normalized chunk text (`match_key`: NFKC, ASCII quotes/dashes, collapsed whitespace, lowercase). Evidence split across two chunks is **not** a hit; such cases are logged as failures.
- **Hit@1** = questions whose top-1 chunk is a hit / N. **Evidence Hit@3** = questions with at least one hit in top-3 / N. Always reported as n/N, separately for dev and test.

## Strategy selection criteria (pre-registered; uses dev only)

1. Highest **dev Evidence Hit@3**.
2. If tied (difference ≤ 1 question, i.e. ≤ 1/16), take the higher **dev Hit@1**.
3. If still tied, take the cheaper strategy: fewer chunks, then lower ingest time.
4. **C vs B:** prefer C if its Hit@3 on the dev filter questions is not lower than B's (C ≡ B on non-filter questions).

The test split is run **once** for all strategies after the choice above is fixed, and reported as is.

## Manual audit sample (pre-registered)

- **Chunk coherence (10 positions per strategy):** sort all 78 counted pages and take every 8th page (index 0, 8, …, 72). That gives pages **59, 67, 75, 83, 98, 106, 114, 341, 349, 357**. On each page the position is the character offset `len(page_text) // 2` in the normalized page text. For each strategy, the chunk covering that offset is scored 0/1/2.
- **Metadata usefulness and grounding:** all 6 test questions × top-3 for each strategy, scored manually by the author.
