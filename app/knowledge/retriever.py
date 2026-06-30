"""混合检索器 — 语义 + 关键词 + ATA 过滤."""

import re
from typing import Optional


class HybridRetriever:
    """混合检索器。

    组合：
    1. 向量语义搜索（ChromaDB）
    2. 关键词匹配（ATA 章节号等）
    3. 结果去重 + 排序
    """

    def __init__(self, vector_store, embedder):
        self.store = vector_store
        self.embedder = embedder

    def retrieve(self, query: str, top_k: int = 10,
                 ata_filter: Optional[str] = None,
                 file_filter: Optional[str] = None) -> list[dict]:
        """执行混合检索。

        Args:
            query: 查询文本
            top_k: 返回结果数
            ata_filter: 可选，过滤特定 ATA 章节
            file_filter: 可选，过滤特定文件

        Returns:
            [{id, text, metadata, score}, ...]
        """
        # 1. 语义搜索
        query_emb = self.embedder.embed_query(query)

        where = None
        if ata_filter:
            where = {"ata_chapter": ata_filter}
        elif file_filter:
            where = {"filename": file_filter}

        results = self.store.search(query_emb, top_k=top_k * 2, where=where)

        # 2. 关键词匹配 boost
        keywords = self._extract_keywords(query)
        for r in results:
            keyword_score = self._keyword_match_score(r["text"], keywords)
            r["score"] = r["score"] * 0.7 + keyword_score * 0.3

        # 3. 排序 + 去重
        seen = set()
        unique = []
        for r in sorted(results, key=lambda x: x["score"], reverse=True):
            key = r["text"][:100]
            if key not in seen:
                seen.add(key)
                unique.append(r)
            if len(unique) >= top_k:
                break

        return unique

    def search_by_ata(self, ata_chapter: str, top_k: int = 5) -> list[dict]:
        """按 ATA 章节检索。"""
        query_emb = self.embedder.embed_query(f"ATA {ata_chapter} maintenance")
        return self.store.search(
            query_emb, top_k=top_k,
            where={"ata_chapter": ata_chapter},
        )

    def _extract_keywords(self, query: str) -> list[str]:
        """提取查询中的关键词：
        - ATA 章节号（如 32-41-03）
        - 数字编号
        - 大写英文缩写
        """
        keywords = []

        # ATA 模式
        ata_matches = re.findall(r"\d{2}[-.]?\d{2}[-.]?\d{2}", query)
        keywords.extend(ata_matches)

        # 大写缩写（如 APU, AOG, MEL）
        abbr = re.findall(r"\b[A-Z]{2,6}\b", query)
        keywords.extend(abbr)

        return keywords

    def _keyword_match_score(self, text: str, keywords: list[str]) -> float:
        """计算关键词匹配得分（0~1）。"""
        if not keywords:
            return 0.0
        text_lower = text.lower()
        matches = sum(1 for kw in keywords if kw.lower() in text_lower)
        return matches / len(keywords)
