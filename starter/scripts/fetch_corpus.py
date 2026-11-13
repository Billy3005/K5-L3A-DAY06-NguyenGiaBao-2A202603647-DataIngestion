"""Download the corpus PDF and verify it is the exact snapshot used in this lab.

The PDF (~28 MB) is not committed; this script makes the corpus reproducible.
Run from starter/:  python scripts/fetch_corpus.py
"""
import hashlib
import sys
import urllib.request
from pathlib import Path

URL = "https://assets.openstax.org/oscms-prodcms/media/documents/principles-microeconomics-3e_-_WEB.pdf"
SHA256 = "65a1856faa91d5fdef9c630928029c6e4e188a9580d9128fcbc9138c4f4a583f"
DEST = Path(__file__).resolve().parents[1] / "data" / "raw" / "principles-microeconomics-3e_-_WEB.pdf"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    DEST.parent.mkdir(parents=True, exist_ok=True)
    if not DEST.exists():
        print(f"Downloading {URL}")
        urllib.request.urlretrieve(URL, DEST)
    actual = sha256(DEST)
    if actual != SHA256:
        # OpenStax may publish a newer errata build at the same URL; fail loudly
        # instead of silently using different page content.
        sys.exit(f"SHA-256 mismatch: expected {SHA256}, got {actual}. "
                 "The upstream PDF changed; page numbers/evidence must be re-verified.")
    print(f"OK {DEST.name} sha256={actual}")


if __name__ == "__main__":
    main()
