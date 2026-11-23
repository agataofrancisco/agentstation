"""Memoria semantica (ChromaDB): colecao por tenant, filtrada por utilizador e validade.

Embeddings: hashing de bigramas (deterministico, sem rede). Aproximacao de demonstracao;
trocar por um modelo de embeddings e uma mudanca local a esta classe.
"""

from __future__ import annotations

import hashlib
import math
import re
import time
import uuid
from dataclasses import dataclass

import chromadb

DIM = 256
_TOKEN = re.compile(r"[a-z0-9]+")


def embed(text: str) -> list[float]:
    tokens = _TOKEN.findall(text.lower())
    grams = tokens + [f"{a} {b}" for a, b in zip(tokens, tokens[1:], strict=False)]
    vec = [0.0] * DIM
    for g in grams:
        h = int(hashlib.sha256(g.encode("utf-8")).hexdigest(), 16)
        vec[h % DIM] += 1.0 if (h >> 8) % 2 == 0 else -1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


@dataclass(frozen=True)
class Memory:
    id: str
    tenant_id: str
    user_id: str
    text: str
    source_task: str
    created_at: float
    expires_at: float
    distance: float | None = None


class MemoryStore:
    def __init__(self, path: str) -> None:
        self._client = chromadb.PersistentClient(path=path)

    def _col(self, tenant_id: str):
        return self._client.get_or_create_collection(
            name=f"mem_{tenant_id}", embedding_function=None, metadata={"hnsw:space": "cosine"}
        )

    def add(
        self,
        *,
        tenant_id: str,
        user_id: str,
        text: str,
        source_task: str,
        ttl_days: int,
        memory_id: str | None = None,
        now: float | None = None,
    ) -> str:
        now = now or time.time()
        mid = memory_id or f"mem-{uuid.uuid4().hex[:16]}"
        self._col(tenant_id).upsert(
            ids=[mid],
            embeddings=[embed(text)],
            documents=[text],
            metadatas=[
                {
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "source_task": source_task,
                    "created_at": now,
                    "expires_at": now + ttl_days * 86400,
                }
            ],
        )
        return mid

    def search(
        self, *, tenant_id: str, user_id: str, query: str, k: int = 3, now: float | None = None
    ) -> list[Memory]:
        now = now or time.time()
        col = self._col(tenant_id)
        if col.count() == 0:
            return []
        res = col.query(
            query_embeddings=[embed(query)],
            n_results=min(k, col.count()),
            where={
                "$and": [
                    {"user_id": {"$eq": user_id}},
                    {"expires_at": {"$gt": now}},
                ]
            },
        )
        return [
            self._to_memory(mid, doc, meta, dist)
            for mid, doc, meta, dist in zip(
                res["ids"][0],
                res["documents"][0],
                res["metadatas"][0],
                res["distances"][0],
                strict=False,
            )
        ]

    def list_for_user(
        self, *, tenant_id: str, user_id: str, now: float | None = None
    ) -> list[Memory]:
        now = now or time.time()
        res = self._col(tenant_id).get(
            where={
                "$and": [
                    {"user_id": {"$eq": user_id}},
                    {"expires_at": {"$gt": now}},
                ]
            }
        )
        return [
            self._to_memory(mid, doc, meta, None)
            for mid, doc, meta in zip(res["ids"], res["documents"], res["metadatas"], strict=False)
        ]

    def get(self, *, tenant_id: str, memory_id: str) -> Memory | None:
        res = self._col(tenant_id).get(ids=[memory_id])
        if not res["ids"]:
            return None
        return self._to_memory(res["ids"][0], res["documents"][0], res["metadatas"][0], None)

    def delete(self, *, tenant_id: str, user_id: str, memory_id: str) -> bool:
        """So o dono apaga. Outro utilizador (mesmo tenant) recebe False, como se nao existisse."""
        mem = self.get(tenant_id=tenant_id, memory_id=memory_id)
        if mem is None or mem.user_id != user_id:
            return False
        self._col(tenant_id).delete(ids=[memory_id])
        return True

    @staticmethod
    def _to_memory(mid: str, doc: str, meta: dict, dist: float | None) -> Memory:
        return Memory(
            id=mid,
            tenant_id=str(meta.get("tenant_id", "")),
            user_id=str(meta.get("user_id", "")),
            text=str(doc or ""),
            source_task=str(meta.get("source_task", "")),
            created_at=float(meta.get("created_at", 0.0)),
            expires_at=float(meta.get("expires_at", 0.0)),
            distance=dist,
        )
