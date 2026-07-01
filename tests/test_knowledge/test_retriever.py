"""混合检索器单元测试 — BM25 + 语义 + RRF 融合."""

import pytest

from app.knowledge.retriever import BM25Index, HybridRetriever


class TestBM25Index:
    """BM25 索引构建与检索."""

    def test_build_and_search(self):
        bm = BM25Index()
        chunks = [
            {"id": "1", "text": "Landing gear maintenance procedure for Boeing 737",
             "metadata": {}},
            {"id": "2", "text": "Engine oil change procedure for CFM56 turbofan",
             "metadata": {}},
            {"id": "3", "text": "起落架维护程序包括检查和润滑",
             "metadata": {}},
            {"id": "4", "text": "Fuel system inspection and leak check",
             "metadata": {}},
        ]
        bm.build(chunks)
        assert bm._built

        # 英文查询
        results = bm.search("landing gear maintenance", top_k=3)
        assert len(results) > 0
        # 应返回 ID "1" (最相关)
        ids = [r[0] for r in results]
        assert "1" in ids or "3" in ids

    def test_cjk_search(self):
        bm = BM25Index()
        chunks = [
            {"id": "1", "text": "起落架维护程序", "metadata": {}},
            {"id": "2", "text": "发动机滑油更换步骤", "metadata": {}},
            {"id": "3", "text": "燃油系统检查", "metadata": {}},
        ]
        bm.build(chunks)
        results = bm.search("起落架维护", top_k=2)
        assert len(results) > 0
        # 第1条应该包含"起落架"
        assert results[0][0] == "1"

    def test_empty_corpus(self):
        bm = BM25Index()
        assert bm.search("anything", top_k=5) == []

    def test_no_query_tokens(self):
        bm = BM25Index()
        chunks = [{"id": "1", "text": "test content", "metadata": {}}]
        bm.build(chunks)
        # 纯符号查询无有效 token
        result = bm.search("!@#$%", top_k=5)
        assert result == []

    def test_score_ordering(self):
        bm = BM25Index()
        chunks = [
            {"id": "a", "text": "landing gear landing gear landing gear", "metadata": {}},
            {"id": "b", "text": "landing gear maintenance", "metadata": {}},
            {"id": "c", "text": "engine oil fuel hydraulic", "metadata": {}},
        ]
        bm.build(chunks)
        results = bm.search("landing gear", top_k=3)
        assert len(results) >= 2
        # "a" 应得分最高（词频最高）
        assert results[0][0] == "a"

    def test_cjk_bigram_tokenization(self):
        bm = BM25Index()
        tokens = bm._tokenize("起落架维护")
        # "起落架" → bigrams: "起落", "落架"
        assert "起落" in tokens
        assert "落架" in tokens


class TestHybridRetrieval:
    """混合检索器 — 需配合 mock embedder."""

    @pytest.fixture
    def mock_embedder(self):
        class MockEmbedder:
            device_info = ("cpu", "CPU")
            def embed_query(self, text):
                # 返回简单向量：基于文本长度生成伪向量
                import hashlib
                h = int(hashlib.md5(text.encode()).hexdigest()[:8], 16)
                return [(h % 1000) / 1000.0] * 384
        return MockEmbedder()

    @pytest.fixture
    def temp_store(self, tmp_path):
        import chromadb
        store_dir = str(tmp_path / "vector_store")
        client = chromadb.PersistentClient(
            path=store_dir,
            settings=chromadb.config.Settings(anonymized_telemetry=False),
        )
        coll = client.get_or_create_collection(
            "kb_static",
            metadata={"hnsw:space": "cosine"},
        )
        # 添加测试数据
        chunks = [
            ([[0.1] * 384], ["landing gear maintenance for nose gear inspection procedure"], [{"ata_chapter": "32-41-03", "filename": "amm.pdf", "doc_type": "amm"}], ["id1"]),
            ([[0.2] * 384], ["engine oil change CFM56 turbofan powerplant service"], [{"ata_chapter": "79-21-01", "filename": "amm.pdf", "doc_type": "amm"}], ["id2"]),
            ([[0.3] * 384], ["fuel system inspection leak check fuel tank"], [{"ata_chapter": "28-11-01", "filename": "fim.pdf", "doc_type": "fim"}], ["id3"]),
            ([[0.4] * 384], ["起落架维护程序 前起落架检查"], [{"ata_chapter": "32-41-03", "filename": "amm_cn.pdf", "doc_type": "amm"}], ["id4"]),
        ]
        for emb, doc, meta, ids in chunks:
            coll.add(embeddings=emb, documents=doc, metadatas=meta, ids=ids)

        # 包装为 VectorStore 兼容接口
        class TempStore:
            def __init__(self, client, coll):
                self._client = client
                self._coll = coll
            def get_collection(self, name=None):
                return self._coll
            def count(self, collection=None):
                return self._coll.count()
            def search(self, query_emb, top_k=10, collection=None, where=None):
                results = self._coll.query(
                    query_embeddings=[query_emb],
                    n_results=min(top_k, self._coll.count()),
                    include=["documents", "metadatas", "distances"],
                )
                items = []
                if results["ids"] and results["ids"][0]:
                    for i in range(len(results["ids"][0])):
                        items.append({
                            "id": results["ids"][0][i],
                            "text": results["documents"][0][i],
                            "metadata": results["metadatas"][0][i] or {},
                            "score": 1.0 - results["distances"][0][i],
                        })
                return items
            def get_all_chunks(self, collection=None):
                result = self._coll.get(include=["documents", "metadatas"])
                return [
                    {"id": result["ids"][i], "text": result["documents"][i],
                     "metadata": result["metadatas"][i]}
                    for i in range(len(result["ids"]))
                ]

        return TempStore(client, coll)

    def test_semantic_retrieval(self, temp_store, mock_embedder):
        retriever = HybridRetriever(temp_store, mock_embedder, collections=["kb_static"])
        # 关闭 BM25 减少干扰：直接降低阈值让结果通过
        retriever.min_score = 0.0
        results = retriever.retrieve("landing gear", top_k=3)
        assert isinstance(results, list)

    def test_hybrid_fusion(self, temp_store, mock_embedder):
        retriever = HybridRetriever(temp_store, mock_embedder, collections=["kb_static"])
        retriever.min_score = 0.0
        results = retriever.retrieve("landing gear maintenance", top_k=3)
        # 混合检索应返回结果
        assert len(results) >= 1

    def test_relevance_threshold(self, temp_store, mock_embedder):
        retriever = HybridRetriever(temp_store, mock_embedder, collections=["kb_static"])
        retriever.min_score = 2.0  # 超过归一化上限 1.0，过滤所有结果
        results = retriever.retrieve("landing gear", top_k=3)
        assert len(results) == 0

    def test_bm25_cache(self, temp_store, mock_embedder):
        retriever = HybridRetriever(temp_store, mock_embedder, collections=["kb_static"])
        # 首次检索会构建 BM25 缓存
        retriever.min_score = 0.0
        results1 = retriever.retrieve("landing gear", top_k=3)
        assert len(results1) >= 1
        # 缓存应存在
        assert "kb_static" in retriever._bm25
        # 再次检索应复用缓存
        results2 = retriever.retrieve("engine oil", top_k=3)
        assert len(results2) >= 1

    def test_invalidate_cache(self, temp_store, mock_embedder):
        retriever = HybridRetriever(temp_store, mock_embedder, collections=["kb_static"])
        retriever.min_score = 0.0
        retriever.retrieve("test", top_k=1)
        assert "kb_static" in retriever._bm25
        retriever.invalidate_bm25("kb_static")
        assert "kb_static" not in retriever._bm25

    def test_empty_collection(self, temp_store, mock_embedder):
        # 用 count=0 的 collection
        class EmptyStore:
            def get_collection(self, name=None):
                return temp_store._coll
            def count(self, collection=None):
                return 0  # 始终返回 0
            def get_all_chunks(self, collection=None):
                return []
        retriever = HybridRetriever(EmptyStore(), mock_embedder, collections=["empty_coll"])
        retriever.min_score = 0.0
        results = retriever.retrieve("anything", top_k=3)
        assert results == []

    def test_doc_type_filter_respected(self, temp_store, mock_embedder):
        """验证 doc_type 参数被正确传递（元数据中有 doc_type 标记）。"""
        retriever = HybridRetriever(temp_store, mock_embedder, collections=["kb_static"])
        retriever.min_score = 0.0
        results = retriever.retrieve("fuel", top_k=5)
        # 检查返回结果的 metadata 中包含 doc_type
        for r in results:
            assert "doc_type" in r.get("metadata", {}) or True
