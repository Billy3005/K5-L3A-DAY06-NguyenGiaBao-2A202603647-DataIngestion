"""Build the corpus manifest from the PDF's own bookmark outline.

Counting rule (applied automatically, not by hand):
  For each selected chapter, count physical PDF pages from the chapter's first
  page up to the page BEFORE its "Key Terms" bookmark. This keeps the narrative
  sections and excludes end-of-chapter material (Key Terms, Key Concepts and
  Summary, Self-Check/Review/Critical Thinking Questions, Problems), plus the
  cover, front matter, contents, appendices, answer key, references and index.

Chapter and section values come from the PDF outline (publisher-provided), so
metadata used for filtering is not guessed.

Run from starter/:  python scripts/build_manifest.py
Outputs (repo root): data/manifest.csv, data/manifest_pages.csv
"""
import csv
import re
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
PDF = ROOT / "starter" / "data" / "raw" / "principles-microeconomics-3e_-_WEB.pdf"
SELECTED_CHAPTERS = [3, 4, 14]

SOURCE = {
    "source_id": "openstax-micro-3e",
    "title": "Principles of Microeconomics 3e (OpenStax)",
    "source_path_or_url": "https://assets.openstax.org/oscms-prodcms/media/documents/principles-microeconomics-3e_-_WEB.pdf",
    "details_url": "https://openstax.org/details/books/principles-microeconomics-3e",
    "license_or_permission": (
        "CC BY-NC-SA 4.0 (c) Rice University/OpenStax; attribution 'Access for free at openstax.org'. "
        "Portions of the Demand and Supply chapter derived from Lumen Learning 'Why It Matters: "
        "Government in Action' (CC BY 4.0). Non-commercial educational use."
    ),
    "accessed_at": "2026-11-13",
    "version": "3e WEB PDF, CreationDate 2026-04-20, sha256 65a1856f...4a583f",
}


def outline_entries(reader: PdfReader):
    """Yield (depth, title, page_number_1based) for the first two outline levels."""
    def walk(items, depth):
        for item in items:
            if isinstance(item, list):
                if depth < 1:
                    yield from walk(item, depth + 1)
            else:
                yield depth, item.title.strip(), reader.get_destination_page_number(item) + 1
    yield from walk(reader.outline, 0)


def chapter_layout(reader: PdfReader):
    """Return {chapter_no: {title, start, key_terms, sections:[(title, start)]}}."""
    chapters, current = {}, None
    for depth, title, page in outline_entries(reader):
        match = re.match(r"Chapter (\d+) (.+)", title)
        if depth == 0:
            current = None
            if match:
                current = int(match.group(1))
                chapters[current] = {"title": match.group(2), "start": page, "sections": []}
        elif current is not None:
            if title == "Key Terms":
                chapters[current]["key_terms"] = page
            elif re.match(r"\d+\.\d+ ", title) or title.startswith("Introduction"):
                chapters[current]["sections"].append((title, page))
    return chapters


def main() -> None:
    reader = PdfReader(PDF)
    layout = chapter_layout(reader)
    page_rows, source_rows = [], []
    for number in SELECTED_CHAPTERS:
        chapter = layout[number]
        first, last = chapter["start"], chapter["key_terms"] - 1
        sections = chapter["sections"]
        chapter_chars = 0
        for page in range(first, last + 1):
            # A page belongs to every section whose span overlaps it.
            on_page = [title for i, (title, start) in enumerate(sections)
                       if start <= page and (i + 1 == len(sections) or sections[i + 1][1] >= page)]
            text = reader.pages[page - 1].extract_text() or ""
            chapter_chars += len(text)
            page_rows.append({
                "page_id": f"micro3e-p{page:04d}",
                "source_id": SOURCE["source_id"],
                "page": page,
                "chapter": number,
                "chapter_title": chapter["title"],
                "sections": " | ".join(on_page),
                "raw_chars": len(text),
                "empty": len(text.strip()) == 0,
            })
        source_rows.append({
            **SOURCE,
            "chapter": number,
            "chapter_title": chapter["title"],
            "physical_pages_in_pdf": len(reader.pages),
            "counted_pages": f"{first}-{last}",
            "counted_page_count": last - first + 1,
            "excluded_in_chapter": f"{chapter['key_terms']}+ (Key Terms, summary, exercises)",
            "raw_chars": chapter_chars,
        })

    out = ROOT / "data"
    with (out / "manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(source_rows[0]))
        writer.writeheader()
        writer.writerows(source_rows)
    with (out / "manifest_pages.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(page_rows[0]))
        writer.writeheader()
        writer.writerows(page_rows)

    total = sum(r["counted_page_count"] for r in source_rows)
    empty = sum(r["empty"] for r in page_rows)
    for r in source_rows:
        print(f"Ch{r['chapter']:>2} {r['chapter_title']:<32} pages {r['counted_pages']:<8} "
              f"n={r['counted_page_count']:<3} raw_chars={r['raw_chars']}")
    print(f"TOTAL content pages = {total} (minimum 30) | empty pages = {empty}")


if __name__ == "__main__":
    main()
