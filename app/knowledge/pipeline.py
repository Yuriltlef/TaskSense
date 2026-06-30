"""知识库构建流水线 — 编排加载→分块→向量化→存储."""

import json
from pathlib import Path

from app.knowledge.loader import PDFLoader
from app.knowledge.chunker import TextChunker
from app.knowledge.embedder import Embedder
from app.knowledge.store import VectorStore
from app.knowledge.retriever import HybridRetriever


class KnowledgePipeline:
    """知识库流水线。

    管理文档加载、分块、嵌入、存储的完整流程。
    支持增量构建（已有向量不重复处理）。
    """

    def __init__(self, data_dir: str = "data"):
        # 确保使用绝对路径
        base = Path(__file__).parent.parent.parent  # app/knowledge → TaskSense/
        self.data_dir = base / data_dir
        self.loader = PDFLoader(str(self.data_dir / "knowledge_base"))
        self.chunker = TextChunker()
        self.embedder = Embedder()
        self.store = VectorStore(str(self.data_dir / "vector_store"))
        self.retriever = HybridRetriever(self.store, self.embedder)

    def build_knowledge_base(self, force: bool = False) -> dict:
        """构建/重建知识库。

        Args:
            force: 是否强制重建（清空已有数据）

        Returns:
            {files, chunks, status}
        """
        if force:
            self.store.clear()

        existing_count = self.store.count()
        if existing_count > 0:
            return {
                "status": "already_built",
                "chunks": existing_count,
                "message": f"知识库已有 {existing_count} 条记录，使用 force=True 强制重建",
            }

        # 1. 加载
        docs = self.loader.load_all()
        if not docs:
            return {"status": "empty", "chunks": 0, "message": "未找到 PDF 文件"}

        # 2. 分块
        all_chunks = []
        for doc in docs:
            chunks = self.chunker.chunk_document(doc)
            all_chunks.extend(chunks)

        if not all_chunks:
            return {"status": "empty", "chunks": 0, "message": "无可提取文本"}

        # 3. 向量化
        texts = [c["text"] for c in all_chunks]
        print(f"[Pipeline] Embedding {len(texts)} chunks...", flush=True)
        embeddings = self.embedder.embed_documents(texts)

        # 4. 存储
        added = self.store.add_chunks(all_chunks, embeddings)

        return {
            "status": "built",
            "files_processed": len(docs),
            "chunks_created": len(all_chunks),
            "chunks_stored": added,
        }

    def search(self, query: str, top_k: int = 5,
               ata_filter: str = None) -> list[dict]:
        """搜索知识库。"""
        return self.retriever.retrieve(query, top_k, ata_filter)

    def get_stats(self) -> dict:
        """知识库统计。"""
        return {
            **self.loader.get_stats(),
            "chunks_stored": self.store.count(),
        }
