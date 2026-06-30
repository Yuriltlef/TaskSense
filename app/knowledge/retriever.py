"""混合检索器 — 多 Collection 语义搜索 + RRF 融合."""

import re
from typing import Optional


class HybridRetriever:
    """多知识库混合检索器。

    - 并行搜索多个 collection
    - RRF (Reciprocal Rank Fusion) 融合排序
    - 关键词匹配 boost
    """

    def __init__(self, vector_store, embedder,
                 collections: list[str] = None):
        self.store = vector_store
        self.embedder = embedder
        self.collections = collections or ["kb_static", "kb_live"]

    def retrieve(self, query: str, top_k: int = 10,
                 collections: list[str] = None,
                 ata_filter: Optional[str] = None) -> list[dict]:
        """多源检索 + RRF 融合。

        Args:
            query: 查询文本
            top_k: 返回结果数
            collections: 指定搜索哪些 collection（默认全部）
            ata_filter: ATA 章节过滤
        """
        sources = collections or self.collections
        query_emb = self.embedder.embed_query(query)

        all_results = []
        for coll_name in sources:
            try:
                where = None
                if ata_filter and coll_name == "kb_static":
                    where = {"ata_chapter": ata_filter}
                results = self.store.search(
                    query_emb, top_k=top_k * 2, collection=coll_name, where=where)
                for r in results:
                    r["collection"] = coll_name
                all_results.append(results)
            except Exception:
                pass

        if not all_results:
            return []

        # RRF 融合
        merged = self._rrf_fusion(all_results)

        # 关键词 boost
        keywords = self._extract_keywords(query)
        for r in merged:
            kw_score = self._keyword_match_score(r["text"], keywords)
            r["score"] = r["score"] * 0.7 + kw_score * 0.3

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

    def _rrf_fusion(self, ranked_lists: list[list[dict]], k: int = 60) -> list[dict]:
        """Reciprocal Rank Fusion: score = sum(1 / (k + rank))"""
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
            v["item"]["score"] = v["score"] / max_rrf  # normalize
            result.append(v["item"])
        return result

    def _extract_keywords(self, query: str) -> list[str]:
        kw = []
        kw.extend(re.findall(r"\d{2}[-.]?\d{2}[-.]?\d{2}", query))
        kw.extend(re.findall(r"\b[A-Z]{2,6}\b", query))
        return kw

    def _keyword_match_score(self, text: str, keywords: list[str]) -> float:
        if not keywords:
            return 0.0
        text_lower = text.lower()
        return sum(1 for kw in keywords if kw.lower() in text_lower) / len(keywords)
