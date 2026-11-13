"""Extract + normalize all counted pages into data/processed/pages.jsonl.

This normalized text is what benchmark evidence is verified against and what
every strategy chunks, so all strategies share exactly the same corpus.
Run from starter/:  python -m scripts.extract_pages
"""
import csv
import json
from pathlib import Path

from src.ingestion import load_page_manifest, load_pdf

STARTER = Path(__file__).resolve().parents[1]
ROOT = STARTER.parent
PDF = STARTER / "data" / "raw" / "principles-microeconomics-3e_-_WEB.pdf"
OUT = STARTER / "data" / "processed" / "pages.jsonl"
LOG = STARTER / "results" / "ingest_log.csv"
DOCUMENT_ID = "openstax-micro-3e"
SOURCE = "openstax/principles-microeconomics-3e_-_WEB.pdf"
ATTRIBUTION = ("Principles of Microeconomics 3e, OpenStax (Rice University), CC BY-NC-SA 4.0. "
               "Access for free at openstax.org")


def main() -> None:
    manifest = load_page_manifest(ROOT / "data" / "manifest_pages.csv")
    log: list[dict] = []
    pages = load_pdf(PDF, DOCUMENT_ID, SOURCE, sorted(manifest), manifest, log)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as handle:
        for page in pages:
            handle.write(json.dumps({"document_id": page.document_id, "source": page.source,
                                     "page": page.page, "text": page.text, **page.metadata,
                                     "attribution": ATTRIBUTION}, ensure_ascii=False) + "\n")
    with LOG.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(log[0]))
        writer.writeheader()
        writer.writerows(log)
    chars = [p.text for p in pages]
    empty = [row["page"] for row in log if row["status"] != "ok"]
    print(f"pages={len(pages)} normalized_chars={sum(map(len, chars))} "
          f"min={min(map(len, chars))} max={max(map(len, chars))} empty={empty}")


if __name__ == "__main__":
    main()
