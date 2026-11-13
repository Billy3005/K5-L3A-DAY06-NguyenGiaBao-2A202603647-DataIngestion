"""Strategy A: fixed-size character windows. Strategy B: structure-aware paragraphs.

Design rules shared by both strategies (controlled comparison):
  * Chunks never cross a page boundary, so `page` metadata is always exact.
  * chunk.text == page.text[start_char:end_char]; offsets are kept in metadata so
    any chunk can be traced back to the exact span of its source page.
  * Chunk IDs are deterministic (page_id + strategy tag + index), so re-ingesting the
    same corpus yields the same IDs (idempotent upsert in the store).
"""
import re
from typing import Any

from .models import Chunk, DocumentPage

_TERMINAL = re.compile(r"[.?!:;\"')\]]$")
_SENTENCE_SPLIT = re.compile(r"(?<=[.?!])\s+(?=[A-Z\"(•])")
_SECTION_TITLE = re.compile(r"^(\d+\.\d+ |Introduction)")


def _block_spans(page: DocumentPage) -> list[dict[str, Any]]:
    """Blocks with their [start, end) offsets in page.text and the section they belong to."""
    spans, offset = [], 0
    section = (page.metadata.get("sections") or [""])[0]
    for block in page.metadata["blocks"]:
        if block["kind"] == "section_heading" and _SECTION_TITLE.match(block["text"]):
            section = block["text"]
        spans.append({**block, "start": offset, "end": offset + len(block["text"]), "section": section})
        offset += len(block["text"]) + 2  # blocks are joined with "\n\n"
    return spans


def _section_at(spans: list[dict[str, Any]], offset: int) -> str:
    current = spans[0]["section"] if spans else ""
    for span in spans:
        if span["start"] > offset:
            break
        current = span["section"]
    return current


def _make_chunk(page: DocumentPage, tag: str, index: int, start: int, end: int,
                section: str, extra: dict[str, Any]) -> Chunk:
    page_id = page.metadata.get("page_id", f"p{page.page:04d}")
    return Chunk(
        chunk_id=f"{page_id}-{tag}-{index:03d}",
        document_id=page.document_id,
        source=page.source,
        page=page.page,
        text=page.text[start:end],
        metadata={"chapter": page.metadata.get("chapter"),
                  "chapter_title": page.metadata.get("chapter_title"),
                  "section": section, "start_char": start, "end_char": end, **extra},
    )


def fixed_size(page: DocumentPage, size: int, overlap: int) -> list[Chunk]:
    """Strategy A: raw character windows of `size` with `overlap`, ignoring structure.

    Deliberately naive (may cut words/sentences) - it is the baseline that strategy B
    is compared against. `section` is the section at the window's first character.
    """
    if not 0 <= overlap < size:
        raise ValueError("require 0 <= overlap < size")
    spans, chunks, start = _block_spans(page), [], 0
    tag = f"fx{size}o{overlap}"
    while start < len(page.text):
        end = min(start + size, len(page.text))
        chunks.append(_make_chunk(page, tag, len(chunks), start, end,
                                  _section_at(spans, start), {"strategy_family": "fixed"}))
        if end == len(page.text):
            break
        start = end - overlap
    return chunks


def _repair_paragraphs(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge text blocks that PyMuPDF split mid-sentence (prev has no terminal
    punctuation and next starts lowercase) back into one paragraph."""
    units: list[dict[str, Any]] = []
    for span in spans:
        prev = units[-1] if units else None
        if (prev and prev["kind"] == "text" and span["kind"] == "text"
                and not _TERMINAL.search(prev["text"]) and re.match(r"[a-z(]", span["text"])):
            prev["end"] = span["end"]
            prev["text"] = prev["text"] + " " + span["text"]
            prev["repaired"] = prev.get("repaired", 0) + 1
            continue
        units.append(dict(span))
    return units


def _split_long(unit: dict[str, Any], page_text: str, max_size: int) -> list[tuple[int, int]]:
    """Split an oversized paragraph at sentence boundaries into spans <= max_size
    (a single sentence longer than max_size is hard-cut as a last resort)."""
    text, base = page_text[unit["start"]:unit["end"]], unit["start"]
    cuts = [0] + [m.end() for m in _SENTENCE_SPLIT.finditer(text)] + [len(text)]
    pieces, piece_start = [], 0
    for prev_cut, cut in zip(cuts, cuts[1:]):
        if cut - piece_start > max_size and prev_cut > piece_start:
            pieces.append((piece_start, prev_cut))
            piece_start = prev_cut
    pieces.append((piece_start, len(text)))
    out = []
    for s, e in pieces:
        while e - s > max_size:          # pathological single sentence
            out.append((s, s + max_size))
            s += max_size
        out.append((s, e))
    return [(base + s, base + e) for s, e in out if page_text[base + s:base + e].strip()]


def by_paragraph(page: DocumentPage, max_size: int) -> list[Chunk]:
    """Strategy B: repaired paragraphs grouped up to `max_size` characters.

    * A section heading or subheading always starts a new chunk and stays attached
      to the paragraph(s) that follow it (a heading is never left alone at the end).
    * Paragraphs are packed greedily while the chunk stays <= max_size.
    * A paragraph longer than max_size is split at sentence boundaries.
    * A chunk never spans two sections, so its `section` metadata is unambiguous.
    """
    units = _repair_paragraphs(_block_spans(page))
    tag = f"pb{max_size}"
    chunks: list[Chunk] = []
    current: dict[str, Any] | None = None   # {start, end, section, has_body, repaired}

    def flush() -> None:
        nonlocal current
        if current and page.text[current["start"]:current["end"]].strip():
            chunks.append(_make_chunk(page, tag, len(chunks), current["start"], current["end"],
                                      current["section"], {"strategy_family": "paragraph",
                                                           "repaired_splits": current["repaired"]}))
        current = None

    for unit in units:
        if unit["kind"] in ("section_heading", "subheading"):
            flush()
            current = {"start": unit["start"], "end": unit["end"], "section": unit["section"],
                       "has_body": False, "repaired": 0}
            continue
        pieces = _split_long(unit, page.text, max_size) if unit["end"] - unit["start"] > max_size \
            else [(unit["start"], unit["end"])]
        for start, end in pieces:
            if current and (end - current["start"] > max_size and current["has_body"]
                            or current["section"] != unit["section"]):
                flush()
            if current is None:
                current = {"start": start, "end": end, "section": unit["section"],
                           "has_body": True, "repaired": unit.get("repaired", 0)}
            else:
                current["end"] = end
                current["has_body"] = True
                current["repaired"] += unit.get("repaired", 0)
    flush()
    return chunks
