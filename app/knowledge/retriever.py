"""混合检索器 — 语义搜索 + BM25 关键词检索 + RRF 融合."""

import math
import re
from collections import defaultdict
from typing import Optional


# ═══════════════════════════════════════════════════════════════
# BM25 索引（轻量，内存缓存，无外部依赖）
# ═══════════════════════════════════════════════════════════════

class BM25Index:
    """轻量级 BM25 全文检索索引。

    对混合中英文文本做 tokenization：
    - 英文：按空白分词 + 小写化
    - 中文：逐字 bigram（相邻二字对），捕获局部语义
    - 保留原始英文词 + 中文 bigram 作为索引 token

    参数 k1=1.5, b=0.75 为标准 BM25。
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus: list[str] = []            # 原始文本
        self.chunk_ids: list[str] = []         # 对应的 chunk ID
        self.tokenized: list[list[str]] = []   # token 列表
        self.idf: dict[str, float] = {}
        self.doc_len: list[int] = []
        self.avgdl: float = 0
        self._built = False

    def _tokenize(self, text: str) -> list[str]:
        """混合中英文 tokenize。"""
        tokens = []
        # 英文词（3+ 字母/数字）
        tokens.extend(t.lower() for t in re.findall(r"[a-zA-Z0-9]{2,}", text))
        # 中文字符序列
        cjk = re.findall(r"[一-鿿㐀-䶿]+", text)
        for seq in cjk:
            # 逐字 bigram
            for i in range(len(seq) - 1):
                tokens.append(seq[i:i + 2])
            # 单字也保留（短查询可能只有一个字）
            if len(seq) == 1:
                tokens.append(seq)
        return tokens

    def build(self, chunks: list[dict]):
        """从 [{id, text, metadata}, ...] 构建 BM25 索引。"""
        self.corpus = [c["text"] for c in chunks]
        self.chunk_ids = [c["id"] for c in chunks]
        self.tokenized = [self._tokenize(t) for t in self.corpus]
        self.doc_len = [len(t) for t in self.tokenized]
        self.avgdl = sum(self.doc_len) / max(len(self.doc_len), 1)

        # IDF
        n_docs = len(self.corpus)
        df = defaultdict(int)
        for tokens in self.tokenized:
            for token in set(tokens):
                df[token] += 1
        self.idf = {
            token: math.log((n_docs - freq + 0.5) / (freq + 0.5) + 1)
            for token, freq in df.items()
        }
        self._built = True

    def search(self, query: str, top_k: int = 20) -> list[tuple[str, float]]:
        """BM25 检索，返回 [(chunk_id, score), ...] 按分降序。"""
        if not self._built or not self.corpus:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        scores = []
        for idx, doc_tokens in enumerate(self.tokenized):
            score = 0.0
            dl = self.doc_len[idx]
            # 计算词频
            tf = defaultdict(int)
            for t in doc_tokens:
                tf[t] += 1

            for qt in query_tokens:
                if qt not in self.idf:
                    continue
                idf = self.idf[qt]
                f = tf.get(qt, 0)
                score += idf * (f * (self.k1 + 1)) / (
                    f + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
                )

            if score > 0:
                scores.append((self.chunk_ids[idx], score))

        # 归一化到 [0, 1] 区间（便于 RRF 融合）
        if scores:
            max_s = max(s[1] for s in scores)
            scores = [(cid, s / max_s) for cid, s in scores]

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]


# ═══════════════════════════════════════════════════════════════
# 混合检索器
# ═══════════════════════════════════════════════════════════════

class HybridRetriever:
    """多知识库混合检索器。

    - 语义搜索（ChromaDB embedding 相似度）
    - BM25 全文检索（关键词匹配，内存缓存）
    - RRF 融合两种检索结果
    - 相关性阈值过滤
    """

    def __init__(self, vector_store, embedder,
                 collections: list[str] = None):
        self.store = vector_store
        self.embedder = embedder
        self.collections = collections or ["kb_static", "kb_live"]
        # BM25 索引缓存：per-collection
        self._bm25: dict[str, BM25Index] = {}
        # 索引版本追踪（collection count 变化则重建）
        self._bm25_count: dict[str, int] = {}
        # 默认相关性阈值
        self.min_score: float = 0.30

    # ── 公开接口 ──

    def retrieve(self, query: str, top_k: int = 10,
                 collections: list[str] = None,
                 ata_filter: Optional[str] = None,
                 doc_type: Optional[str] = None) -> list[dict]:
        """多源混合检索 + RRF 融合。

        Args:
            query: 查询文本
            top_k: 返回结果数
            collections: 指定搜索哪些 collection（默认全部）
            ata_filter: ATA 章节过滤（如 "32"）
            doc_type: 文档类型过滤（如 "amm", "amt_handbook"）
        """
        sources = collections or self.collections
        query_emb = self.embedder.embed_query(query)

        # 并行收集语义 + BM25 结果（同一 collection）
        semantic_lists = []
        bm25_lists = []

        for coll_name in sources:
            if self.store.count(coll_name) == 0:
                continue

            # 语义搜索
            try:
                where = None
                if ata_filter and coll_name == "kb_static":
                    where = {"ata_chapter": {"$regex": f"^{ata_filter}"}}
                sem_results = self.store.search(
                    query_emb, top_k=top_k * 2, collection=coll_name, where=where)
                for r in sem_results:
                    r["collection"] = coll_name
                    r["source"] = "semantic"
                semantic_lists.append(sem_results)
            except Exception:
                pass

            # BM25 搜索
            try:
                bm = self._ensure_bm25(coll_name)
                bm_raw = bm.search(query, top_k=top_k * 2)
                # 查找 chunk 详情
                if bm_raw:
                    bm_results = []
                    coll = self.store.get_collection(coll_name)
                    bm_id_map = {cid: score for cid, score in bm_raw}
                    # 批量获取
                    fetched = coll.get(
                        ids=list(bm_id_map.keys()),
                        include=["documents", "metadatas"],
                    )
                    for i, cid in enumerate(fetched["ids"]):
                        if cid in bm_id_map:
                            bm_results.append({
                                "id": cid,
                                "text": fetched["documents"][i] or "",
                                "metadata": fetched["metadatas"][i] or {},
                                "score": bm_id_map[cid],
                                "collection": coll_name,
                                "source": "bm25",
                            })
                    bm_results.sort(key=lambda x: x["score"], reverse=True)
                    bm_lists.append(bm_results)
            except Exception:
                pass

        # 融合
        all_lists = semantic_lists + bm25_lists
        if not all_lists:
            return []

        if len(all_lists) == 1:
            merged = all_lists[0]
        else:
            merged = self._rrf_fusion(all_lists)

        # 相关性阈值过滤
        merged = [r for r in merged if r["score"] >= self.min_score]

        # 去重排序
        seen = set()
        unique = []
        for r in sorted(merged, key=lambda x: x["score"], reverse=True):
            key = r["text"][:120]
            if key not in seen:
                seen.add(key)
                unique.append(r)
            if len(unique) >= top_k:
                break

        return unique

    # ── BM25 缓存管理 ──

    def _ensure_bm25(self, collection: str) -> BM25Index:
        """获取或重建 BM25 索引（自动检测过期）。"""
        current_count = self.store.count(collection)
        if (collection in self._bm25
                and self._bm25_count.get(collection) == current_count):
            return self._bm25[collection]

        # 重建
        bm = BM25Index()
        chunks = self.store.get_all_chunks(collection)
        if chunks:
            bm.build(chunks)
        self._bm25[collection] = bm
        self._bm25_count[collection] = current_count
        return bm

    def invalidate_bm25(self, collection: str = None):
        """清除 BM25 缓存（数据更新后调用）。"""
        if collection:
            self._bm25.pop(collection, None)
            self._bm25_count.pop(collection, None)
        else:
            self._bm25.clear()
            self._bm25_count.clear()

    # ── RRF ──

    def _rrf_fusion(self, ranked_lists: list[list[dict]], k: int = 60) -> list[dict]:
        """RRF (Reciprocal Rank Fusion)。

        与旧版不同：现在同一 chunk 可能出现在语义和 BM25 两个列表中
        （id 相同），RRF 能正确融合双路信号。
        """
        scores = {}
        for lst in ranked_lists:
            for rank, item in enumerate(lst):
                key = item["id"]
                rrf = 1.0 / (k + rank + 1)
                if key not in scores:
                    scores[key] = {"item": item, "score": 0.0}
                scores[key]["score"] += rrf

        result = []
        max_rrf = max(v["score"] for v in scores.values()) if scores else 1.0
        for v in scores.values():
            v["item"]["score"] = v["score"] / max_rrf
            result.append(v["item"])
        return result

    # ── 可选：Cross-Encoder 重排序 ──

    def rerank(self, query: str, candidates: list[dict],
               top_k: int = None) -> list[dict]:
        """使用 Cross-Encoder 对候选结果重排序。

        Args:
            query: 查询文本
            candidates: 初检候选列表
            top_k: 返回数（默认全部）

        Note:
            需要加载 CrossEncoder 模型（约 1-2GB 显存）。
            通过 settings.json rag.rerank_enabled 控制是否启用。
        """
        if not candidates:
            return []

        top_k = top_k or len(candidates)

        try:
            from sentence_transformers import CrossEncoder
        except ImportError:
            return candidates[:top_k]

        try:
            model = CrossEncoder(
                "BAAI/bge-reranker-v2-m3",
                device=self.embedder.device_info[0],
            )
            pairs = [[query, c["text"][:512]] for c in candidates]
            scores = model.predict(pairs, show_progress_bar=False)

            for i, s in enumerate(scores):
                candidates[i]["rerank_score"] = float(s)
                candidates[i]["score"] = float(s)  # 用 rerank 分覆盖

            candidates.sort(key=lambda x: x["score"], reverse=True)
            return candidates[:top_k]
        except Exception:
            return candidates[:top_k]

    # ── 关键词提取（辅助元数据过滤） ──

    @staticmethod
    def _extract_keywords(query: str) -> list[str]:
        """从查询中提取结构化关键词：ATA 编号 + 英文缩写。"""
        kw = []
        kw.extend(re.findall(r"\d{2}[-.]?\d{2}[-.]?\d{2}", query))
        kw.extend(re.findall(r"\b[A-Z]{2,6}\b", query))
        return kw
