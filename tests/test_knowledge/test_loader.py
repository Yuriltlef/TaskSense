"""知识库加载器测试."""

import pytest
from pathlib import Path

from app.knowledge.loader import PDFLoader


class TestPDFLoader:
    def test_list_files(self):
        loader = PDFLoader("data/knowledge_base")
        files = loader.list_files()
        assert len(files) > 0, "知识库目录应包含 PDF 文件"
        for f in files:
            assert f.suffix == ".pdf"

    @pytest.mark.slow
    def test_load_single_file(self):
        loader = PDFLoader("data/knowledge_base")
        files = loader.list_files()
        if not files:
            pytest.skip("无 PDF 文件")

        doc = loader.load_file(files[0])
        assert doc is not None
        assert "text" in doc
        assert "filename" in doc
        assert "title" in doc
        assert "pages" in doc
        assert len(doc["text"]) > 0

    @pytest.mark.slow
    def test_load_first_3_files(self):
        """烟雾测试：仅加载前 3 个 PDF（需 --run-slow）。"""
        loader = PDFLoader("data/knowledge_base")
        files = loader.list_files()
        if not files:
            pytest.skip("无 PDF 文件")

        docs = []
        for f in files[:3]:
            doc = loader.load_file(f)
            assert doc is not None
            assert len(doc["text"]) > 0
            docs.append(doc)
        assert len(docs) > 0

    def test_get_stats(self):
        loader = PDFLoader("data/knowledge_base")
        stats = loader.get_stats()
        assert "total_files" in stats
        assert "total_size_mb" in stats
        assert stats["total_files"] > 0

    def test_nonexistent_dir(self):
        loader = PDFLoader("nonexistent_dir")
        assert loader.list_files() == []


class TestTextChunker:
    def test_chunk_document(self):
        from app.knowledge.chunker import TextChunker

        chunker = TextChunker(chunk_size=500, chunk_overlap=50)
        doc = {
            "text": "This is a test document. " * 100,
            "filename": "test.pdf",
            "title": "Test Document",
        }
        chunks = chunker.chunk_document(doc)
        assert len(chunks) > 0
        for c in chunks:
            assert "text" in c
            assert "metadata" in c
            assert len(c["text"]) > 0

    def test_chunk_with_ata(self):
        from app.knowledge.chunker import TextChunker

        chunker = TextChunker()
        doc = {
            "text": (
                "ATA 32-41-03 Landing Gear Maintenance\n"
                "This section covers nose gear procedures.\n"
                "ATA 32-41-04 Brake System\n"
                "This section covers brake maintenance.\n"
            ) * 10,
            "filename": "amm.pdf",
            "title": "AMM",
        }
        chunks = chunker.chunk_document(doc)
        assert len(chunks) > 0
        # 应该识别出 ATA 章节
        ata_chunks = [c for c in chunks if c["metadata"].get("ata_chapter")]
        assert len(ata_chunks) > 0

    def test_empty_text(self):
        from app.knowledge.chunker import TextChunker

        chunker = TextChunker()
        doc = {"text": "", "filename": "empty.pdf", "title": "Empty"}
        chunks = chunker.chunk_document(doc)
        assert len(chunks) <= 1  # 空文本不产生有效分块
