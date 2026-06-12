"""Agentic RAG — Chroma vector store over supply-chain SOPs and policies."""

from __future__ import annotations

import hashlib
from typing import Any

from src.config import Settings

# Seed knowledge base — domain semantic layer for supply-chain agents.
_SEED_DOCS = [
    {
        "id": "sop-inventory-reorder",
        "text": "Reorder SOP: When SKU quantity falls below reorder_point, create a "
                "replenishment request. Analysts may query stock levels but cannot "
                "modify reorder thresholds without manager approval.",
        "metadata": {"type": "sop", "domain": "inventory"},
    },
    {
        "id": "policy-pii-handling",
        "text": "PII Policy: Customer emails and phone numbers must not be exported "
                "to external URLs. Bulk reads over 100 records require data-owner approval.",
        "metadata": {"type": "policy", "domain": "security"},
    },
    {
        "id": "sop-shipment-delay",
        "text": "Shipment delay protocol: Check carrier status, notify affected DCs, "
                "escalate to logistics lead if delay exceeds 48 hours.",
        "metadata": {"type": "sop", "domain": "logistics"},
    },
    {
        "id": "policy-refund-limits",
        "text": "Refund policy: Single-order refunds within order value are allowed. "
                "Mass refunds or scope=all operations require finance approval.",
        "metadata": {"type": "policy", "domain": "finance"},
    },
    {
        "id": "sop-demand-forecast",
        "text": "Demand forecasting: Use 8-week rolling average for baseline. "
                "Seasonal adjustments require demand planner sign-off.",
        "metadata": {"type": "sop", "domain": "planning"},
    },
]


class KnowledgeBase:
    """Vector RAG with Chroma; keyword fallback when Chroma unavailable."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = None
        self._collection = None
        self._keyword_index = _SEED_DOCS
        self._init_chroma()

    def _init_chroma(self) -> None:
        try:
            import chromadb
            self._client = chromadb.HttpClient(
                host=self._settings.chroma_host,
                port=self._settings.chroma_port,
            )
            self._collection = self._client.get_or_create_collection(
                name="supply_chain_sops",
                metadata={"hnsw:space": "cosine"},
            )
            if self._collection.count() == 0:
                self._collection.add(
                    ids=[d["id"] for d in _SEED_DOCS],
                    documents=[d["text"] for d in _SEED_DOCS],
                    metadatas=[d["metadata"] for d in _SEED_DOCS],
                )
        except Exception:
            self._client = None
            self._collection = None

    def retrieve(self, query: str, k: int = 3) -> list[dict[str, Any]]:
        if self._collection is not None:
            try:
                results = self._collection.query(query_texts=[query], n_results=k)
                docs = []
                for i, doc_id in enumerate(results["ids"][0]):
                    docs.append({
                        "id": doc_id,
                        "text": results["documents"][0][i],
                        "metadata": results["metadatas"][0][i],
                        "score": 1 - (results["distances"][0][i] if results.get("distances") else 0),
                    })
                return docs
            except Exception:
                pass
        return self._keyword_fallback(query, k)

    def _keyword_fallback(self, query: str, k: int) -> list[dict[str, Any]]:
        tokens = set(query.lower().split())
        scored = []
        for doc in self._keyword_index:
            doc_tokens = set(doc["text"].lower().split())
            overlap = len(tokens & doc_tokens)
            if overlap:
                scored.append((overlap, doc))
        scored.sort(key=lambda x: -x[0])
        return [
            {"id": d["id"], "text": d["text"], "metadata": d["metadata"], "score": s / 10}
            for s, d in scored[:k]
        ]

    def health(self) -> str:
        if self._collection is not None:
            try:
                self._collection.count()
                return "connected"
            except Exception:
                return "error"
        return "keyword_fallback"
