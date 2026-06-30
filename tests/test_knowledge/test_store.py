"""向量存储测试."""

import pytest

from app.knowledge.store import VectorStore


class TestVectorStore:
    @pytest.fixture
    def store(self):
        s = VectorStore(
            persist_dir="data/vector_store",
            collection_name="test_collection",
        )
        yield s
        # 清理
        try:
            s.client.delete_collection("test_collection")
        except Exception:
            pass

    def test_init(self, store):
        assert store.count() >= 0

    def test_add_and_search(self, store):
        store.clear()

        chunks = [
            {
                "text": "Landing gear maintenance procedure for nose gear",
                "metadata": {"ata_chapter": "32-41-03", "filename": "amm.pdf"},
            },
            {
                "text": "Engine oil change procedure for CFM56",
                "metadata": {"ata_chapter": "79-21-01", "filename": "amm.pdf"},
            },
        ]
        # 使用简单随机向量替代真实 embedding
        embeddings = [
            [0.1] * 384,
            [0.2] * 384,
        ]

        count = store.add_chunks(chunks, embeddings)
        assert count == 2
        assert store.count() == 2

        # 搜索
        query_emb = [0.15] * 384  # 接近第一个块
        results = store.search(query_emb, top_k=2)
        assert len(results) > 0
        for r in results:
            assert "text" in r
            assert "metadata" in r
            assert "score" in r

    def test_clear(self, store):
        store.clear()
        assert store.count() == 0
