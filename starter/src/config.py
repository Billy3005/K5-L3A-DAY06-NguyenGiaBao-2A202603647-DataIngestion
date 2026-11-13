"""Single source of truth for the three strategies and shared settings.

A vs B changes ONLY the chunking. B vs C changes ONLY the metadata filter
(C reuses B's chunks/index and applies a filter only when a question has one).
"""
from pathlib import Path

STARTER = Path(__file__).resolve().parents[1]
ROOT = STARTER.parent
PAGES_JSONL = STARTER / "data" / "processed" / "pages.jsonl"
QUESTIONS = ROOT / "benchmark" / "questions.jsonl"
RESULTS = STARTER / "results"

EMBEDDING_MODEL = "intfloat/multilingual-e5-base"
EMBEDDING_DIM = 768
EMBEDDING_MAX_TOKENS = 512
QUERY_PREFIX = "query: "      # required by the e5 model card
PASSAGE_PREFIX = "passage: "
TOP_K = 3

STRATEGIES = {
    "A": {"chunking": "fixed", "size": 500, "overlap": 50, "index": "A", "use_filter": False,
          "hypothesis": "Baseline: fixed windows cut sentences/evidence, lowering Hit@1 and coherence."},
    "B": {"chunking": "paragraph", "max_size": 1000, "index": "B", "use_filter": False,
          "hypothesis": "Paragraph+heading chunks keep evidence whole and add context, raising Hit@3 and coherence."},
    "C": {"chunking": "paragraph", "max_size": 1000, "index": "B", "use_filter": True,
          "hypothesis": "Same chunks as B; chapter filter removes cross-chapter distractors on filter questions."},
}
