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
        embeddings = self.embed(documents)
        try:
            collection = self.chroma.get_or_create_collection(
                self.collection_name(knowledge_base_id),
                metadata={
                    "embedding_model": self.settings.ollama_embed_model,
                    "hnsw:space": "cosine",
                },
            )
            stored_model = (collection.metadata or {}).get("embedding_model")
            if stored_model != self.settings.ollama_embed_model:
                raise VectorStoreError(
                    f"知识库向量模型为 {stored_model or '未知'}，当前模型为 "
                    f"{self.settings.ollama_embed_model}，请重建索引"
                )
            collection.upsert(
                ids=ids,
                embeddings=cast(Any, embeddings),
                documents=documents,
                metadatas=cast(Any, metadatas),
            )
        except VectorStoreError:
            raise
        except Exception as exc:  # Chroma exposes transport-specific exception classes.
            raise VectorStoreError(f"Chroma 写入失败：{exc}") from exc

    def delete_entry(self, knowledge_base_id: str, entry_id: str) -> None:
        try:
            self.chroma.get_collection(self.collection_name(knowledge_base_id)).delete(
                ids=[entry_id]
            )
        except Exception as exc:  # Chroma exposes transport-specific exception classes.
            if "does not exist" not in str(exc).lower():
                raise VectorStoreError(f"Chroma 删除知识条目失败：{exc}") from exc

    def delete_knowledge_base(self, knowledge_base_id: str) -> None:
        try:
            self.chroma.delete_collection(self.collection_name(knowledge_base_id))
        except Exception as exc:  # Chroma exposes transport-specific exception classes.
            if "does not exist" not in str(exc).lower():
                raise VectorStoreError(f"Chroma 删除知识库失败: {exc}") from exc

    def query(self, knowledge_base_id: str, text: str, limit: int = 5) -> list[dict[str, Any]]:
        embeddings = self.embed([text])
        try:
            collection = self.chroma.get_collection(self.collection_name(knowledge_base_id))
            stored_model = (collection.metadata or {}).get("embedding_model")
            if stored_model != self.settings.ollama_embed_model:
                raise VectorStoreError(
                    f"知识库向量模型为 {stored_model or '未知'}，当前模型为 "
                    f"{self.settings.ollama_embed_model}，请重建索引"
                )
            result = collection.query(
                query_embeddings=cast(Any, embeddings),
                n_results=limit,
                include=["documents", "metadatas", "distances"],
            )
        except VectorStoreError:
            raise
        except Exception as exc:  # Chroma exposes transport-specific exception classes.
            raise VectorStoreError(f"Chroma 检索失败：{exc}") from exc
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
