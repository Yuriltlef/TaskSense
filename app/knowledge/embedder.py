"""文本向量化 — 自动检测 CUDA/CPU，优化显存与批处理。

离线模式由 main.py 在最早阶段设置环境变量保证。
"""


def _detect_device():
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda", torch.cuda.get_device_name(0)
        if torch.backends.mps.is_available():
            return "mps", "Apple MPS"
    except ImportError:
        pass
    return "cpu", "CPU"


class Embedder:
    """文本向量化器。默认 BAAI/bge-m3，离线加载，自动 CUDA/MPS/CPU。"""

    QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "
    DOC_INSTRUCTION = "Represent this document for retrieval: "

    def __init__(self, model_name: str = "BAAI/bge-m3", local_files_only: bool = True):
        self.model_name = model_name
        self._model = None
        self._dim = None
        self._is_bge = "bge" in model_name.lower()
        self._device, self._device_name = _detect_device()
        self._local_only = local_files_only

    @property
    def device_info(self) -> tuple[str, str]:
        return self._device, self._device_name

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(
                self.model_name, device=self._device,
                local_files_only=self._local_only,
            )
        return self._model

    @property
    def dimension(self) -> int:
        if self._dim is None:
            self._dim = self.model.get_sentence_embedding_dimension() or 1024
        return self._dim

    def _auto_batch_size(self) -> int:
        """根据设备自动选择 batch size。"""
        if self._device == "cuda":
            try:
                import torch
                gb = torch.cuda.get_device_properties(0).total_memory / 1024**3
                return max(1, min(64, int((gb - 2.5) * 8)))
            except Exception:
                return 16
        return 64  # CPU

    def embed_documents(self, texts: list[str],
                        batch_size: int = None,
                        show_progress: bool = True) -> list[list[float]]:
        """批量向量化文档。自动选择 batch_size 和优化。"""
        if not texts:
            return []

        if batch_size is None:
            batch_size = self._auto_batch_size()

        # BGE models benefit from document-side instruction prefix
        if self._is_bge:
            texts = [self.DOC_INSTRUCTION + t for t in texts]

        if self._device == "cuda":
            import torch
            with torch.no_grad():
                embeddings = self.model.encode(
                    texts, batch_size=batch_size,
                    show_progress_bar=show_progress,
                    normalize_embeddings=True,
                    convert_to_tensor=True,
                )
                if embeddings.device.type == "cuda":
                    embeddings = embeddings.cpu()
                torch.cuda.empty_cache()
                return embeddings.float().tolist()

        # CPU / MPS
        embeddings = self.model.encode(
            texts, batch_size=batch_size,
            show_progress_bar=show_progress,
            normalize_embeddings=True,
        )
        return embeddings.tolist()

    def embed_query(self, text: str) -> list[float]:
        """向量化查询。BGE 模型添加 instruction 前缀。"""
        if self._is_bge:
            text = self.QUERY_INSTRUCTION + text

        if self._device == "cuda":
            import torch
            with torch.no_grad():
                result = self.model.encode(
                    [text], normalize_embeddings=True, convert_to_tensor=True)
                if result.device.type == "cuda":
                    result = result.cpu()
                torch.cuda.empty_cache()
                return result.float().tolist()[0]

        result = self.model.encode([text], normalize_embeddings=True)
        return result[0].tolist()
