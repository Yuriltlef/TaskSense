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

    def test_get_all_chunks(self, store):
        store.clear()
        chunks = [
            {"text": "Chunk A for testing", "metadata": {"idx": 0}},
            {"text": "Chunk B for testing", "metadata": {"idx": 1}},
            {"text": "Chunk C for testing", "metadata": {"idx": 2}},
        ]
        embeddings = [[0.1] * 384, [0.2] * 384, [0.3] * 384]
        store.add_chunks(chunks, embeddings)
        all_c = store.get_all_chunks()
        assert len(all_c) == 3
        for c in all_c:
            assert "id" in c
            assert "text" in c
            assert "metadata" in c

    def test_get_all_chunks_empty(self, store):
        store.clear()
        all_c = store.get_all_chunks()
        assert all_c == []

    def test_delete_collection(self, store):
        # 创建临时 collection 并添加数据
        store.get_collection("temp_to_delete")
        store.add_chunks(
            [{"text": "temp", "metadata": {"source": "test"}}],
            [[0.5] * 384],
            collection="temp_to_delete",
        )
        assert store.count("temp_to_delete") == 1
        store.delete_collection("temp_to_delete")
        # 删除后 collection 不再存在于列表中
        remaining = store.list_collections()
        assert "temp_to_delete" not in remaining, (
            f"Collection still in list: {remaining}"
        )

    def test_delete_nonexistent_collection(self, store):
        # 不应抛出异常
        result = store.delete_collection("nonexistent_collection_xyz")
        assert result is False
