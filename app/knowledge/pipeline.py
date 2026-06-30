"""知识库流水线 — 多 Collection 冷热分离."""

import json
from pathlib import Path

from app.knowledge.loader import PDFLoader
from app.knowledge.chunker import TextChunker
from app.knowledge.embedder import Embedder
from app.knowledge.store import VectorStore
from app.knowledge.retriever import HybridRetriever


class KnowledgePipeline:
    """知识库流水线 — 支持多 Collection。

    kb_static: PDF 知识库（AMM/FIM/AD），构建一次，很少重建
    kb_live:   任务日志/工单，增量追加
    """

    DEFAULT_COLLECTIONS = ["kb_static", "kb_live"]

    def __init__(self, data_dir: str = "data"):
        base = Path(__file__).parent.parent.parent
        self.data_dir = base / data_dir
        self.loader = PDFLoader(str(self.data_dir / "knowledge_base"))
        self.chunker = TextChunker()
        self.embedder = Embedder()
        self.store = VectorStore(str(self.data_dir / "vector_store"))
        self.retriever = HybridRetriever(
            self.store, self.embedder, self.DEFAULT_COLLECTIONS)

    def build_knowledge_base(self, force: bool = False,
                             collection: str = "kb_static") -> dict:
        """构建/重建知识库。

        kb_static: 从 processed/ 文本构建（force=True 清空重建）
        kb_live:   增量追加（不清空）
        """
        if force:
            self.store.clear(collection)

        existing = self.store.count(collection)
        if existing > 0 and collection == "kb_static" and not force:
            return {"status": "already_built", "chunks": existing}

        if collection == "kb_static":
            return self._build_from_files(collection)

        return {"status": "empty", "chunks": 0,
                "message": "kb_live uses add_chunks() for incremental adds"}

    def _build_from_files(self, collection: str) -> dict:
        """从 processed/ 文本文件构建。"""
        txt_dir = self.data_dir / "knowledge_base" / "processed"
        txt_files = sorted(txt_dir.glob("*.txt"))

        if not txt_files:
            # 尝试直接从 PDF 构建
            docs = self.loader.load_all()
            if not docs:
                return {"status": "empty", "chunks": 0,
                        "message": "No PDF or text files found"}
            all_chunks = []
            for doc in docs:
                all_chunks.extend(self.chunker.chunk_document(doc))
        else:
            all_chunks = []
            for tf in txt_files:
                meta_path = tf.with_suffix(".json")
                meta = json.loads(meta_path.read_text(encoding="utf-8")) \
                    if meta_path.exists() else {}
                text = tf.read_text(encoding="utf-8")
                all_chunks.extend(self.chunker.chunk_document({
                    "text": text,
                    "filename": meta.get("filename", tf.name),
                    "title": meta.get("title", tf.stem),
                }))

        if not all_chunks:
            return {"status": "empty", "chunks": 0,
                    "message": "No text to chunk"}

        texts = [c["text"] for c in all_chunks]
        embeddings = self.embedder.embed_documents(texts)
        added = self.store.add_chunks(all_chunks, embeddings, collection)

        return {
            "status": "built",
            "collection": collection,
            "chunks_created": len(all_chunks),
            "chunks_stored": added,
        }

    def add_logs(self, texts: list[str],
                 metadatas: list[dict] = None) -> int:
        """增量追加任务日志到 kb_live。每次加一条或几条。"""
        if not texts:
            return 0

        if metadatas is None:
            metadatas = [{"source": "task_log"} for _ in texts]

        chunks = [
            {"text": t, "metadata": m}
            for t, m in zip(texts, metadatas)
        ]
        embeddings = self.embedder.embed_documents(texts)
        return self.store.add_chunks(chunks, embeddings, "kb_live")

    def search(self, query: str, top_k: int = 10,
               collections: list[str] = None,
               ata_filter: str = None) -> list[dict]:
        """多源检索。"""
        return self.retriever.retrieve(
            query, top_k, collections, ata_filter)

    def get_stats(self) -> dict:
        """所有 collection 统计。"""
        stats = {}
        for coll in self.DEFAULT_COLLECTIONS:
            stats[coll] = self.store.count(coll)
        stats["total"] = sum(stats.values())
        stats["collections"] = self.store.list_collections()
        return stats
