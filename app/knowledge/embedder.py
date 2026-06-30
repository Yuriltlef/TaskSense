"""文本向量化 — 使用 sentence-transformers 本地模型."""


class Embedder:
    """文本向量化器。

    默认: BAAI/bge-m3（1024 维，中英多语，MTEB 高分）。
    BGE 模型查询时需要添加 instruction 前缀。
    """

    QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "

    def __init__(self, model_name: str = "BAAI/bge-m3"):
        self.model_name = model_name
        self._model = None
        self._dim = None
        self._is_bge = "bge" in model_name.lower()

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
        return self._model

    @property
    def dimension(self) -> int:
        if self._dim is None:
            self._dim = self.model.get_sentence_embedding_dimension() or 1024
        return self._dim

    def embed_documents(self, texts: list[str],
                        batch_size: int = 32) -> list[list[float]]:
        """批量向量化文档（不带 instruction 前缀）。"""
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
        """向量化查询文本（BGE 模型添加 instruction 前缀）。"""
        if self._is_bge:
            text = self.QUERY_INSTRUCTION + text
        result = self.model.encode(
            [text],
            normalize_embeddings=True,
        )
        return result[0].tolist()
