"""文本向量化 — 使用 sentence-transformers 本地模型，自动检测 CUDA."""


def _detect_device():
    """检测最佳计算设备：CUDA > MPS > CPU。"""
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda", torch.cuda.get_device_name(0)
    except ImportError:
        pass
    try:
        import torch
        if torch.backends.mps.is_available():
            return "mps", "Apple MPS"
    except Exception:
        pass
    return "cpu", "CPU"


class Embedder:
    """文本向量化器。

    默认: BAAI/bge-m3（1024 维，中英多语）。
    自动检测 CUDA/MPS/CPU。
    """

    QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "

    def __init__(self, model_name: str = "BAAI/bge-m3"):
        self.model_name = model_name
        self._model = None
        self._dim = None
        self._is_bge = "bge" in model_name.lower()
        self._device, self._device_name = _detect_device()

    @property
    def device_info(self) -> tuple[str, str]:
        return self._device, self._device_name

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(
                self.model_name,
                device=self._device,
            )
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
