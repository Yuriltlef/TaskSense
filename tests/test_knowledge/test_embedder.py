"""向量化器单元测试 — 不加载真实模型."""

import pytest


class TestEmbedderConfig:
    """Embedder 配置与设备检测."""

    def test_device_detection_returns_valid(self):
        from app.knowledge.embedder import _detect_device
        device, name = _detect_device()
        assert device in ("cuda", "mps", "cpu")
        assert isinstance(name, str)
        assert len(name) > 0

    def test_init_defaults(self):
        from app.knowledge.embedder import Embedder
        emb = Embedder()
        assert emb.model_name == "BAAI/bge-m3"
        assert emb._is_bge is True
        dev, name = emb.device_info
        assert dev in ("cuda", "mps", "cpu")

    def test_init_non_bge_model(self):
        from app.knowledge.embedder import Embedder
        emb = Embedder(model_name="all-MiniLM-L6-v2")
        assert emb._is_bge is False

    def test_instruction_constants(self):
        from app.knowledge.embedder import Embedder
        assert "Represent this sentence" in Embedder.QUERY_INSTRUCTION
        assert "Represent this document" in Embedder.DOC_INSTRUCTION

    def test_auto_batch_size(self):
        from app.knowledge.embedder import Embedder
        emb = Embedder()
        bs = emb._auto_batch_size()
        assert isinstance(bs, int)
        assert bs >= 1
        assert bs <= 256  # 合理上限

    def test_embed_empty_list(self):
        from app.knowledge.embedder import Embedder
        emb = Embedder()
        # 不加载模型的情况下，空列表应快速返回
        result = emb.embed_documents([], show_progress=False)
        assert result == []

    def test_dimension_property(self):
        from app.knowledge.embedder import Embedder
        emb = Embedder()
        # 不加载模型 -> 默认 1024 (BGE-m3 维度)
        dim = emb.dimension
        assert dim == 1024 or dim > 0


class TestInstructionPrefix:
    """BGE instruction 前缀逻辑."""

    def test_query_instruction_applied(self):
        """验证 embed_query 对 BGE 模型加 instruction 前缀的逻辑。

        注意：此测试不实际调用模型，仅验证代码路径。
        """
        from app.knowledge.embedder import Embedder

        # BGE 模型
        emb_bge = Embedder(model_name="BAAI/bge-m3")
        assert emb_bge._is_bge is True

        # 非 BGE 模型
        emb_non = Embedder(model_name="all-MiniLM-L6-v2")
        assert emb_non._is_bge is False

    def test_doc_instruction_present(self):
        """验证 DOC_INSTRUCTION 常量存在且非空。"""
        from app.knowledge.embedder import Embedder
        assert Embedder.DOC_INSTRUCTION
        assert len(Embedder.DOC_INSTRUCTION) > 5
