from functools import lru_cache
from typing import Any, cast

import chromadb
import httpx

from app.config import get_settings


class VectorStoreError(RuntimeError):
    pass


class VectorStore:
    """Generate embeddings with Ollama and store explicit vectors in Chroma."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.chroma = chromadb.HttpClient(
            host=self.settings.chroma_host, port=self.settings.chroma_port
        )

    @staticmethod
    def collection_name(knowledge_base_id: str) -> str:
        return f"kb_{knowledge_base_id.replace('-', '_')}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            response = httpx.post(
                f"{self.settings.ollama_base_url}/api/embed",
                json={"model": self.settings.ollama_embed_model, "input": texts},
                timeout=120,
            )
            response.raise_for_status()
            embeddings = response.json().get("embeddings")
        except (httpx.HTTPError, ValueError) as exc:
            raise VectorStoreError(f"Ollama 嵌入服务不可用: {exc}") from exc
        if not isinstance(embeddings, list) or len(embeddings) != len(texts):
            raise VectorStoreError("Ollama 返回的向量数量不正确")
        dimensions = {len(item) for item in embeddings if isinstance(item, list)}
        if len(dimensions) != 1 or not dimensions or 0 in dimensions:
            raise VectorStoreError("Ollama 返回的向量维度不一致")
        return embeddings

    def upsert(
        self,
        knowledge_base_id: str,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        collection = self.chroma.get_or_create_collection(
            self.collection_name(knowledge_base_id),
            metadata={"embedding_model": self.settings.ollama_embed_model, "hnsw:space": "cosine"},
        )
        collection.upsert(
            ids=ids,
            embeddings=cast(Any, self.embed(documents)),
            documents=documents,
            metadatas=cast(Any, metadatas),
        )

    def delete_entry(self, knowledge_base_id: str, entry_id: str) -> None:
        self.chroma.get_collection(self.collection_name(knowledge_base_id)).delete(ids=[entry_id])

    def delete_knowledge_base(self, knowledge_base_id: str) -> None:
        try:
            self.chroma.delete_collection(self.collection_name(knowledge_base_id))
        except Exception as exc:  # Chroma exposes transport-specific exception classes.
            if "does not exist" not in str(exc).lower():
                raise

    def query(self, knowledge_base_id: str, text: str, limit: int = 5) -> list[dict[str, Any]]:
        collection = self.chroma.get_collection(self.collection_name(knowledge_base_id))
        result = collection.query(
            query_embeddings=cast(Any, self.embed([text])),
            n_results=limit,
            include=["documents", "metadatas", "distances"],
        )
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        return [
            {"id": item_id, "content": doc, "metadata": meta or {}, "distance": distance}
            for item_id, doc, meta, distance in zip(
                ids, documents, metadatas, distances, strict=False
            )
        ]


@lru_cache
def get_vector_store() -> VectorStore:
    return VectorStore()
