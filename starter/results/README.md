# Results — Day 06

Excerpts of chunk text in this folder come from *Principles of Microeconomics 3e*, OpenStax (Rice University), CC BY-NC-SA 4.0. Access for free at openstax.org.

| File | Produced by | Content |
|---|---|---|
| `versions.txt` | `pip freeze` | Python, library, PostgreSQL and pgvector versions |
| `ingest_log.csv` | `python -m scripts.extract_pages` | Per page: status, normalized characters, blocks, image blocks, dropped header/footer text |
| `chunks/A.jsonl`, `chunks/B.jsonl` | `python -m scripts.make_chunks` | Every chunk with id, page, chapter, section, offsets, token count |
| `chunk_stats.csv` | `python -m scripts.make_chunks` | Chunk count, length and token distribution, mid-word starts, repaired splits |
| `ingest_runs.csv` | `python -m src.run ingest` | One row per index per run: inserted/updated/unchanged/deleted, rows in DB, timings, cost |
| `reingest_check.txt` | `python -m scripts.reingest_check` | Changed-document test in an isolated namespace |

## Storage and ingestion

- **Store:** PostgreSQL 16.16 + pgvector 0.8.7 (Docker `pgvector/pgvector:0.8.7-pg16`, volume `pg_data`). Table `chunks`, primary key `(strategy, chunk_id)`, column `vector(768)`.
- **Search:** cosine (`<=>`), **exact** search (no ANN index), with an index on `(strategy, chapter)` for filtering. C queries index `B` with `WHERE chapter = %s`.
- **Model:** `intfloat/multilingual-e5-base`, 768 dimensions, run locally on CPU with L2-normalized vectors. Prefixes are `passage: ` for chunks and `query: ` for questions. Cost **$0**.

| Run | Index | Chunks | Embedded | Inserted | Unchanged | Rows in DB | Embed s | Total s |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| first ingest | A | 521 | 521 | 521 | 0 | 521 | 70.2 | 71.9 |
| first ingest | B | 326 | 326 | 326 | 0 | 326 | 60.1 | 61.4 |
| re-ingest (same corpus) | A | 521 | 0 | 0 | 521 | 521 | 0.1 | 0.2 |
| re-ingest (same corpus) | B | 326 | 0 | 0 | 326 | 326 | 0.1 | 0.2 |

A takes longer to embed than B because it has 60% more chunks, even though each chunk is shorter. Timings come from one run on a laptop CPU (Intel 12th gen), so they are indicative only.

**Idempotency:** the stable `chunk_id` plus a `content_hash` (sha256 of the model name, text and metadata) means unchanged chunks are neither re-embedded nor duplicated. After the re-ingest, `count(*) = count(DISTINCT chunk_id)` for both indexes.

**Changed documents** (`reingest_check.txt`): when page 85 is edited (one value changed, second half removed), 2 chunks are updated, 2 obsolete chunks are deleted and 5 stay unchanged, so the rows in the DB equal the new chunk set. The upsert and the obsolete-chunk deletion run in one transaction. Removing a whole document requires an explicit delete by `document_id`; that case is not exercised here.

## Ingestion and extraction log (78 pages)

| Item | Count | Handling |
|---|---:|---|
| Empty pages, or pages needing OCR | 0 | — (born-digital PDF) |
| Pages with running header/footer removed | 75 | Dropped by y-position (y ≤ 45pt or y ≥ 745pt). The 3 pages without one (59, 97, 335) are chapter openers, which have no running header. |
| Image blocks (figures) | 52 on 45 pages | Skipped: no OCR of graphs. Figure **captions** are text and are kept. |
| Paragraphs split mid-sentence by PyMuPDF | 61 | Repaired in strategy B (merge when the previous block has no terminal punctuation and the next starts lowercase). Strategy A ignores structure by design. |
| Pages ending mid-sentence (paragraph continues on next page) | 40 | **Not repaired**: chunks never cross pages, so that `page` metadata is exact. Produces short continuation chunks, e.g. p85 `all. Quality is also likely to deteriorate.` — a known coherence failure mode. |
| Line-break hyphenation (`low- skill`) | 13 | **Not fixed**: 3 of the 13 are legitimate suspended hyphens (`middle- and upper-income`), and changing normalization after the benchmark freeze would require re-verification. Negligible impact on embeddings. |
| Table text order | some tables | Table cells are linearized row by row. On p101 (Table 4.2) the "Technology" row label lands mid-text. Kept as is and listed as a limitation. |
| Printed vs physical page number | offset 12 | All `page` values are **physical** PDF pages, 1-based. |

## Chunking statistics (from `chunk_stats.csv`)

| Strategy | Chunks | Total chars | Median len | Max len | Max tokens (limit 512) | Starts mid-word | Dev evidence fully inside one chunk |
|---|---:|---:|---:|---:|---:|---:|---:|
| A fixed 500 / overlap 50 | 521 | 243,562 | 500 | 500 | 150 | 274 (53%) | 12/16 |
| B paragraph ≤ 1000 | 326 | 220,964 | 732 | 1007 | 277 | 0 | 16/16 |
| C | = B (same index) | | | | | | |

- A stores about 10% more characters than the corpus (221,412), because of the overlap.
- B's maximum of 1007 > 1000 is a soft cap: a heading can be attached in front of a ≤ 1000-character body.
- No chunk exceeds the model's 512-token limit, so nothing is silently truncated.
- **Caveat:** evidence quotes are whole sentences. That structurally favours sentence-preserving chunking, so the A–B gap partly reflects this choice.
