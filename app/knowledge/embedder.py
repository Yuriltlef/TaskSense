"""文本向量化 — 使用 sentence-transformers 本地模型."""

from typing import Optional


class Embedder:
    """文本向量化器。

    使用 sentence-transformers 的本地模型（无需 API 调用）。
    默认: all-MiniLM-L6-v2（轻量，384 维，中英文均可）。
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._model = None

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
        return self._model

    @property
    def dimension(self) -> int:
        """嵌入向量维度。"""
        return self.model.get_sentence_embedding_dimension()

    def embed_documents(self, texts: list[str],
                        batch_size: int = 32) -> list[list[float]]:
        """批量向量化文档。

        Args:
            texts: 文本列表
            batch_size: 批大小

        Returns:
            嵌入向量列表
        """
        if not texts:
            return []
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=True,
            normalize_embeddings=True,
        )
        return embeddings.tolist()

    def embed_query(self, text: str) -> list[float]:
        """向量化查询文本。"""
        result = self.model.encode(
            [text],
            normalize_embeddings=True,
        )
        return result[0].tolist()
