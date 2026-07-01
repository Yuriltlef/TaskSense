"""PDF 文档加载器 — 批量加载知识库文件."""

import os
from pathlib import Path
from typing import Optional

from pypdf import PdfReader


class PDFLoader:
    """PDF 加载器。

    从 data/knowledge_base 目录加载所有 PDF，
    提取文本内容并附带元数据。
    """

    def __init__(self, base_dir: str = "data/knowledge_base"):
        self.base_dir = Path(base_dir)

    def list_files(self) -> list[Path]:
        """列出所有 PDF 文件。"""
        if not self.base_dir.exists():
            return []
        return sorted(self.base_dir.glob("*.pdf"))

    def load_all(self) -> list[dict]:
        """加载所有 PDF 文档。

        Returns:
            [{filename, title, text, pages, metadata}, ...]
        """
        docs = []
        for fp in self.list_files():
            doc = self.load_file(fp)
            if doc and doc.get("text"):
                docs.append(doc)
        return docs

    def load_file(self, filepath: Path) -> Optional[dict]:
        """加载单个 PDF 文件。

        Returns:
            {filename, title, text, pages, page_starts, filepath, size_bytes}
            page_starts: list[int] — 每页在 full_text 中的起始字符偏移
        """
        try:
            reader = PdfReader(str(filepath))
            text_parts = []
            page_starts = []  # 每页在全文中起始位置
            offset = 0

            for page_num, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text:
                    cleaned = page_text.strip()
                    text_parts.append(cleaned)
                    page_starts.append(offset)
                    offset += len(cleaned) + 2  # +2 for "\n\n"
                # 空页也记录但 offset 不变

            full_text = "\n\n".join(text_parts)

            if not full_text.strip():
                return None

            # 尝试从文件名提取飞机型号等信息
            filename = filepath.name
            title = filepath.stem.replace("_", " ").replace("-", " ")

            return {
                "filename": filename,
                "title": title,
                "text": full_text,
                "pages": len(reader.pages),
                "page_starts": page_starts,
                "filepath": str(filepath),
                "size_bytes": filepath.stat().st_size,
            }
        except Exception as e:
            print(f"[Loader] Failed to load {filepath.name}: {e}")
            return None

    def get_stats(self) -> dict:
        """获取知识库统计。"""
        docs = self.list_files()
        total_size = sum(f.stat().st_size for f in docs)
        return {
            "total_files": len(docs),
            "total_size_mb": round(total_size / (1024 * 1024), 1),
        }
