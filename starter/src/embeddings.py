"""Real local embedding model: intfloat/multilingual-e5-base via sentence-transformers.

No API key, cost 0. If the model cannot load or produces the wrong shape, this
raises - it never falls back to mock/random vectors.
"""
from typing import Protocol

from .config import EMBEDDING_DIM, EMBEDDING_MAX_TOKENS, EMBEDDING_MODEL, PASSAGE_PREFIX, QUERY_PREFIX


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text, in the same order."""
        ...

    def embed_query(self, question: str) -> list[float]:
        """Return a query vector compatible with the stored document vectors."""
        ...


class E5Embedder:
    """e5 expects 'query: ' / 'passage: ' prefixes; vectors are L2-normalized so
    cosine similarity is well defined (pgvector `<=>` = cosine distance)."""

    def __init__(self, model_name: str = EMBEDDING_MODEL, device: str = "cpu", batch_size: int = 32) -> None:
        from sentence_transformers import SentenceTransformer  # heavy import kept local

        self.model_name = model_name
        self.batch_size = batch_size
        self._model = SentenceTransformer(model_name, device=device)
        self._model.max_seq_length = EMBEDDING_MAX_TOKENS
        self.dimensions = self._model.get_sentence_embedding_dimension()
        if self.dimensions != EMBEDDING_DIM:
            raise RuntimeError(f"{model_name} has {self.dimensions} dims, expected {EMBEDDING_DIM}")

    def _encode(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(texts, batch_size=self.batch_size, normalize_embeddings=True,
                                     convert_to_numpy=True, show_progress_bar=False)
        if vectors.shape != (len(texts), self.dimensions):
            raise RuntimeError(f"unexpected embedding shape {vectors.shape}")
        return vectors.tolist()

    def count_tokens(self, text: str) -> int:
        return len(self._model.tokenizer(text)["input_ids"])

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        prefixed = [PASSAGE_PREFIX + t for t in texts]
        too_long = [i for i, t in enumerate(prefixed) if self.count_tokens(t) > EMBEDDING_MAX_TOKENS]
        if too_long:  # would be silently truncated by the model: refuse instead
            raise ValueError(f"{len(too_long)} passages exceed {EMBEDDING_MAX_TOKENS} tokens, e.g. index {too_long[0]}")
        return self._encode(prefixed)

    def embed_query(self, question: str) -> list[float]:
        return self._encode([QUERY_PREFIX + question])[0]
