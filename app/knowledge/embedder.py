"""文本向量化 — 使用 sentence-transformers 本地模型，自动检测 CUDA."""

import torch


def _detect_device():
    """检测最佳计算设备：CUDA > MPS > CPU。"""
    if torch.cuda.is_available():
        free_gb = (torch.cuda.get_device_properties(0).total_memory
                   - torch.cuda.memory_allocated(0)) / (1024 ** 3)
        return "cuda", torch.cuda.get_device_name(0), free_gb
    try:
        if torch.backends.mps.is_available():
            return "mps", "Apple MPS", None
    except Exception:
        pass
    return "cpu", "CPU", None


class Embedder:
    """文本向量化器。

    默认: BAAI/bge-m3（1024 维，中英多语）。
    自动检测 CUDA/MPS/CPU，CUDA 时启用 FP16 + 小 batch 适配 8GB VRAM。
    """

    QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "

    def __init__(self, model_name: str = "BAAI/bge-m3"):
        self.model_name = model_name
        self._model = None
        self._dim = None
        self._is_bge = "bge" in model_name.lower()
        self._device, self._device_name, self._free_vram_gb = _detect_device()
        self._use_cuda = self._device == "cuda"

    @property
    def device_info(self) -> tuple[str, str]:
        return self._device, self._device_name

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            if self._use_cuda:
                # ── CUDA 路径：FP16 半精度，限制序列长度 ──
                self._model = SentenceTransformer(
                    self.model_name,
                    device="cuda",
                    model_kwargs={"torch_dtype": torch.float16},
                )
                self._model.max_seq_length = 512
            else:
                # ── CPU / MPS 路径：标准 FP32 ──
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
                        batch_size: int | None = None) -> list[list[float]]:
        """批量向量化文档。

        CUDA: batch_size 默认 8, FP16 + no_grad + 每 batch 清缓存
        CPU:  batch_size 默认 32, 直接 encode
        """
        if not texts:
            return []

        if batch_size is None:
            batch_size = 8 if self._use_cuda else 32

        if self._use_cuda:
            # ── CUDA 路径 ──
            with torch.no_grad():
                embeddings = self.model.encode(
                    texts,
                    batch_size=batch_size,
                    show_progress_bar=False,
                    normalize_embeddings=True,
                    convert_to_tensor=True,
                )
                result = embeddings.cpu().to(torch.float32).tolist()
            torch.cuda.empty_cache()
            return result
        else:
            # ── CPU / MPS 路径 ──
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

        if self._use_cuda:
            with torch.no_grad():
                result = self.model.encode(
                    [text],
                    normalize_embeddings=True,
                )
            return result.tolist()
        else:
            result = self.model.encode(
                [text],
                normalize_embeddings=True,
            )
            return result.tolist()
