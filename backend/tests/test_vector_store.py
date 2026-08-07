from types import SimpleNamespace
from typing import Any

import pytest

from app.services.vector_store import VectorStore, VectorStoreError


class FakeCollection:
    def __init__(self, model: str = "qwen3-embedding:0.6b") -> None:
        self.metadata = {"embedding_model": model}
        self.upserted = False

    def upsert(self, **_kwargs: Any) -> None:
        self.upserted = True

    def query(self, **_kwargs: Any) -> dict[str, list[list[Any]]]:
        return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}


class FakeChroma:
    def __init__(self, collection: FakeCollection | None = None, error: Exception | None = None):
        self.collection = collection or FakeCollection()
        self.error = error

    def get_or_create_collection(self, *_args: Any, **_kwargs: Any) -> FakeCollection:
        if self.error:
            raise self.error
        return self.collection

    def get_collection(self, *_args: Any, **_kwargs: Any) -> FakeCollection:
        if self.error:
            raise self.error
        return self.collection


def make_store(chroma: FakeChroma) -> VectorStore:
    store = object.__new__(VectorStore)
    store.settings = SimpleNamespace(ollama_embed_model="qwen3-embedding:0.6b")
    store.chroma = chroma
    store.embed = lambda texts: [[0.1, 0.2] for _ in texts]  # type: ignore[method-assign]
    return store


def test_upsert_wraps_chroma_transport_error() -> None:
    store = make_store(FakeChroma(error=RuntimeError("connection refused")))

    with pytest.raises(VectorStoreError, match="Chroma 写入失败"):
        store.upsert("kb", ["id"], ["内容"], [{}])


def test_query_rejects_embedding_model_mismatch() -> None:
    store = make_store(FakeChroma(FakeCollection(model="旧模型")))

    with pytest.raises(VectorStoreError, match="请重建索引"):
        store.query("kb", "问题与回复")
