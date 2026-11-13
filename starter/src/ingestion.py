"""Read and normalize the PDF corpus page by page, keeping source/page traceability.

Extraction uses PyMuPDF text blocks (one block ~ one paragraph) instead of plain
pypdf text, because pypdf loses paragraph boundaries that strategy B needs.
"""
import csv
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

import pymupdf

from .models import DocumentPage

# Running header sits at y~24-34pt, footer ("Access for free at openstax.org") at
# y~758-768pt on a 792pt page; body text lives between ~50 and ~730pt.
HEADER_MAX_Y = 45.0
FOOTER_MIN_Y = 745.0
HEADING_FONT = "Archivo-SemiBold"
SECTION_HEADING_SIZE = 13.0      # e.g. "3.1 Demand, Supply, and Equilibrium ..."
SUBHEADING_SIZE = 10.8           # e.g. "What Factors Affect Demand?"

_CHAR_MAP = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "­": "", "​": "", "﻿": "",
})


def normalize_text(text: str) -> str:
    """NFKC + ASCII quotes/dashes, then collapse whitespace inside one block.

    Paragraph structure is preserved by the caller (blocks are joined with a
    blank line); this function only cleans the text of a single block.
    """
    text = unicodedata.normalize("NFKC", text).translate(_CHAR_MAP)
    return re.sub(r"\s+", " ", text).strip()


def match_key(text: str) -> str:
    """Canonical form for evidence matching: normalized, whitespace-collapsed, lowercase."""
    return normalize_text(text).lower()


def _block_kind(block: dict[str, Any]) -> str:
    first = block["lines"][0]["spans"][0]
    if first["font"] == HEADING_FONT and first["size"] >= SECTION_HEADING_SIZE - 0.1:
        return "section_heading"
    if first["font"] == HEADING_FONT and abs(first["size"] - SUBHEADING_SIZE) < 0.1:
        return "subheading"
    return "text"


def load_pdf(path: Path, document_id: str, source: str, pages: list[int],
             page_metadata: dict[int, dict[str, Any]] | None = None,
             log: list[dict[str, Any]] | None = None) -> list[DocumentPage]:
    """Extract the selected physical pages (1-based) as normalized DocumentPages.

    Each page keeps `blocks` (kind + text) in metadata so structure-aware chunking
    can use paragraph and heading boundaries. Empty pages, dropped header/footer
    lines and image blocks are recorded in `log` instead of being silently lost.
    """
    page_metadata = page_metadata or {}
    log = log if log is not None else []
    result: list[DocumentPage] = []
    with pymupdf.open(path) as doc:
        for number in pages:
            page = doc[number - 1]
            blocks, dropped, images = [], [], 0
            for block in page.get_text("dict", sort=True)["blocks"]:
                if block["type"] != 0:
                    images += 1
                    continue
                raw = "\n".join("".join(s["text"] for s in line["spans"]) for line in block["lines"])
                text = normalize_text(raw)
                if not text:
                    continue
                y0, y1 = block["bbox"][1], block["bbox"][3]
                if y1 <= HEADER_MAX_Y or y0 >= FOOTER_MIN_Y:
                    dropped.append(text)
                    continue
                blocks.append({"kind": _block_kind(block), "text": text})
            page_text = "\n\n".join(b["text"] for b in blocks)
            meta = dict(page_metadata.get(number, {}))
            meta["blocks"] = blocks
            result.append(DocumentPage(document_id=document_id, source=source, page=number,
                                       text=page_text, metadata=meta))
            log.append({"page": number, "status": "empty" if not page_text else "ok",
                        "chars": len(page_text), "blocks": len(blocks), "image_blocks": images,
                        "dropped_header_footer": " || ".join(dropped)})
    return result


def read_pages_jsonl(path: Path) -> list[DocumentPage]:
    """Load the normalized pages produced by scripts/extract_pages.py."""
    pages = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            meta = {k: v for k, v in row.items() if k not in ("document_id", "source", "page", "text")}
            pages.append(DocumentPage(row["document_id"], row["source"], row["page"], row["text"], meta))
    return pages


def load_page_manifest(path: Path) -> dict[int, dict[str, Any]]:
    """Read data/manifest_pages.csv -> {page: {page_id, chapter, chapter_title, sections}}."""
    with path.open(encoding="utf-8") as handle:
        return {int(row["page"]): {"page_id": row["page_id"], "chapter": int(row["chapter"]),
                                   "chapter_title": row["chapter_title"],
                                   "sections": row["sections"].split(" | ")}
                for row in csv.DictReader(handle)}
