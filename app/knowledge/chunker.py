"""文本分块器 — 语义感知 + ATA 层级感知."""

import re
from typing import Optional


class TextChunker:
    """文本分块器。

    策略：
    - 优先按 ATA 章节号分段（如 "32-41-03"）
    - 其次按自然段落边界分段
    - 每块 ~800 tokens，重叠 ~120 tokens
    """

    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 120):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_document(self, doc: dict) -> list[dict]:
        """将一篇文档分块。

        Returns:
            [{text, metadata}, ...]
        """
        text = doc.get("text", "")
        filename = doc.get("filename", "")

        # 尝试按 ATA 章节分段
        ata_chunks = self._split_by_ata(text)
        if len(ata_chunks) > 1:
            result = []
            for ata_code, ata_text in ata_chunks:
                sub_chunks = self._chunk_text(ata_text)
                for i, sub in enumerate(sub_chunks):
                    result.append({
                        "text": sub,
                        "metadata": {
                            "filename": filename,
                            "title": doc.get("title", ""),
                            "ata_chapter": ata_code,
                            "chunk_index": i,
                            "source": "ata_section",
                        },
                    })
            return result

        # 否则按普通文本分块
        chunks = self._chunk_text(text)
        return [
            {
                "text": c,
                "metadata": {
                    "filename": filename,
                    "title": doc.get("title", ""),
                    "ata_chapter": "",
                    "chunk_index": i,
                    "source": "generic",
                },
            }
            for i, c in enumerate(chunks)
        ]

    def _split_by_ata(self, text: str) -> list[tuple[str, str]]:
        """按 ATA 章节号分割文本。

        匹配模式：
        - "ATA 32-41-03"
        - "CHAPTER 32"
        - "32-41-03"
        - "32.41.03"
        """
        # 尝试匹配带标题的章节
        pattern = r"(?:ATA\s+|CHAPTER\s+|CH\.\s*)?(\d{2}[-.]?\d{2}[-.]?\d{2})\b"
        matches = list(re.finditer(pattern, text, re.IGNORECASE))

        if not matches:
            # 尝试更简单的两数字模式 (ATA Chapter)
            pattern = r"(?:Chapter|CHAPTER|ATA)\s+(\d{2})\b"
            matches = list(re.finditer(pattern, text, re.IGNORECASE))

        if len(matches) < 2:
            return [(text[:50][:30] or "GENERAL", text)]

        result = []
        for i, match in enumerate(matches):
            code = match.group(1).replace(".", "-")
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            result.append((code, text[start:end].strip()))

        # 添加匹配前的文本
        if matches and matches[0].start() > 0:
            prefix = text[: matches[0].start()].strip()
            if prefix:
                result.insert(0, ("PREAMBLE", prefix))

        return result

    def _chunk_text(self, text: str) -> list[str]:
        """按 token 数量分块，尊重句子边界。"""
        # 粗略估计：1 token ≈ 4 字符（中文）或 0.75 词（英文）
        sentences = re.split(r"(?<=[。！？.!?\n])\s*", text)
        chunks = []
        current = []
        current_len = 0

        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            sent_len = len(sent)  # 简化的 token 长度估计

            if current_len + sent_len > self.chunk_size * 4 and current:
                chunks.append(" ".join(current))
                # 重叠：保留上一个 chunk 末尾的句子作为新 chunk 的开头
                prev = list(current)         # 先保存再清空
                current = []
                overlap_len = 0
                for s in reversed(prev):
                    overlap_len += len(s)
                    current.insert(0, s)
                    if overlap_len > self.chunk_overlap * 4:
                        break

            current.append(sent)
            current_len += sent_len

        if current:
            chunks.append(" ".join(current))

        return chunks if chunks else [text]
