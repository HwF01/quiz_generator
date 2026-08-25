from __future__ import annotations

from rank_bm25 import BM25Okapi

from app.services.llm.embed import embed_local, cosine


def tokenize(text: str) -> list[str]:
    return [ch for ch in text if ch.strip()]


class SQARetrieval:
    """Sparse + dense hybrid retrieval with RRF fusion for builtin knowledge."""

    def __init__(self, documents: list[dict]):
        self.documents = documents
        self.corpus = [tokenize(d["text"]) for d in documents]
        self.bm25 = BM25Okapi(self.corpus) if self.corpus else None
        self.vectors = [embed_local(d["text"]) for d in documents]

    def search(self, query: str, k: int = 5) -> list[dict]:
        if not self.documents:
            return []
        tokens = tokenize(query)
        sparse_rank = []
        if self.bm25:
            scores = self.bm25.get_scores(tokens)
            sparse_rank = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        qv = embed_local(query)
        dense_rank = sorted(
            range(len(self.vectors)),
            key=lambda i: cosine(qv, self.vectors[i]),
            reverse=True,
        )
        rrf: dict[int, float] = {}
        for ranks in (sparse_rank, dense_rank):
            for r, idx in enumerate(ranks):
                rrf[idx] = rrf.get(idx, 0) + 1.0 / (60 + r)
        ordered = sorted(rrf.items(), key=lambda x: x[1], reverse=True)[:k]
        return [self.documents[i] for i, _ in ordered]


_GLOBAL: SQARetrieval | None = None


def get_retriever(documents: list[dict]) -> SQARetrieval:
    global _GLOBAL
    _GLOBAL = SQARetrieval(documents)
    return _GLOBAL
