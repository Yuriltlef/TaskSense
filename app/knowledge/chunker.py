"""文本分块器 — 内容自适应，支持 ATA 文档 + 通用文档混合场景."""

import re
from typing import Optional

# 页码标记（内部使用，分块后移除）
_PAGE_MARKER_RE = re.compile(r"\[\[PAGE:(\d+)\]\]")

# ATA 章节验证集（来自 app.config.constants.ATA_CHAPTERS 的两码前缀）
_VALID_ATA_PREFIXES = frozenset({
    "05", "12",
    "21", "22", "23", "24", "25", "26", "27", "28", "29",
    "30", "31", "32", "33", "34", "35", "36", "38",
    "49",
    "52", "53", "57",
    "71", "72", "73", "74", "79", "80",
})

# 文档类型推断规则：(关键词, doc_type)
_DOC_TYPE_RULES = [
    (r"(?i)(?:^|[^a-z])amm(?:[^a-z]|$)|amm[_ ]|aircraft\s*maintenance\s*manual", "amm"),
    (r"(?i)(?:^|[^a-z])fim(?:[^a-z]|$)|fim[_ ]|fault.?isolation|troubleshoot(?:ing)?", "fim"),
    (r"(?i)airworthiness\s*directive|(?<![a-z])ad[._-]?\d{4}", "ad"),
    (r"(?i)(?:^|[^a-z])ac[_\-.]|aircraft[-_\s]*characteristics|airplane\s*characteristics", "ac"),
    (r"(?i)(?:^|[^a-z])amt(?:[^a-z]|$)|amt[_ ]|airframe.*handbook|powerplant.*handbook|general.*handbook", "amt_handbook"),
    (r"(?i)(?:^|[^a-z])sb(?:[^a-z]|$)|sb[_ ]|service\s*bulletin", "sb"),
    (r"(?i)(?:^|[^a-z])cao(?:[^a-z]|$)|cao[._]|(?<![a-z])easa|foreign\s*part.?\s*145|civil[-_\s]*aviation[-_\s]*(?:order|regulation)", "regulation"),
    (r"(?i)航空器维修|维修.{0,5}教材", "textbook"),
    (r"(?i)(?:^|[^a-z])ipc(?:[^a-z]|$)|ipc[_ ]|illustrated\s*parts", "ipc"),
    (r"(?i)(?:^|[^a-z])srm(?:[^a-z]|$)|srm[_ ]|structural\s*repair", "srm"),
    (r"(?i)(?:^|[^a-z])wdm(?:[^a-z]|$)|wdm[_ ]|wiring\s*diagram", "wdm"),
    (r"(?i)(?:^|[^a-z])mel(?:[^a-z]|$)|mel[_ ]|minimum\s*equipment\s*list", "mel"),
]


def _detect_doc_type(filename: str, text_preview: str = "") -> str:
    """从文件名和文本片段推断文档类型。"""
    combined = (filename + " " + text_preview[:500]).lower()
    for pattern, dtype in _DOC_TYPE_RULES:
        if re.search(pattern, combined):
            return dtype
    return "general"


class TextChunker:
    """内容自适应文本分块器。

    策略（按优先级）：
    1. 预处理：修复 PDF 导致的断行，规范化空白
    2. 章节检测：ATA 验证匹配 → 通用标题模式 → 双换行段落边界
    3. Token 感知分块：CJK 友好的 token 估算
    4. 后处理：过滤过小块、合并相邻短节段、文档类型标注
    """

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 80):
        self.chunk_size = chunk_size          # tokens
        self.chunk_overlap = chunk_overlap    # tokens
        self.min_chunk_chars = 100            # 最小字符数（低于此值的 chunk 丢弃）

    # ── 入口 ──

    def chunk_document(self, doc: dict) -> list[dict]:
        """将一篇文档分块。

        支持 page_starts（loader 提供）用于追踪页码。

        Returns:
            [{text, metadata}, ...]  metadata 包含:
            filename/title/ata_chapter/section_title/
            chapter/section/part (结构化章节编号)/
            page_start/page_end/doc_type/chunk_index/source
        """
        text = doc.get("text", "")
        filename = doc.get("filename", "")
        title = doc.get("title", "")
        page_starts = doc.get("page_starts", [])

        if not text.strip():
            return []

        # 注入页码标记（在预处理之前）
        text = self._inject_page_markers(text, page_starts)

        # 预处理
        text = self._preprocess_text(text)

        # 文档类型
        doc_type = _detect_doc_type(filename, text[:1000])

        base_meta = {
            "filename": filename,
            "title": title,
            "doc_type": doc_type,
            "page_start": 1,
            "page_end": max(1, len(page_starts)),
            "ata_chapter": "",
            "section_title": "",
            "chapter": None,
            "section": None,
            "part": None,
        }

        # 尝试章节检测 → 分块
        sections = self._detect_sections(text)
        if len(sections) <= 1:
            # 无结构化章节 — 直接按段落/固定窗口分块
            chunks = self._chunk_text(text)
            result = []
            for i, c in enumerate(chunks):
                meta = dict(base_meta)
                meta["chunk_index"] = i
                meta["source"] = "paragraph"
                # 提取页码范围
                ps, pe = self._extract_page_range(c)
                meta["page_start"] = ps or meta["page_start"]
                meta["page_end"] = pe or meta["page_end"]
                # 移除页码标记
                c = _PAGE_MARKER_RE.sub("", c).strip()
                result.append({"text": c, "metadata": meta})
            return result

        # 有章节 — 每节独立分块
        result = []
        for section_label, section_text in sections:
            section_info = self._extract_section_info(section_label)
            is_ata = self._is_ata_label(section_label)
            sub_chunks = self._chunk_text(section_text)
            for i, sub in enumerate(sub_chunks):
                meta = dict(base_meta)
                meta["chunk_index"] = i
                meta["source"] = "ata_section" if is_ata else "heading"
                meta["ata_chapter"] = section_label if is_ata else ""
                meta["section_title"] = section_info.get("title", section_label[:100])
                meta["chapter"] = section_info.get("chapter")
                meta["section"] = section_info.get("section")
                meta["part"] = section_info.get("part")
                # 提取页码范围
                ps, pe = self._extract_page_range(sub)
                meta["page_start"] = ps or meta["page_start"]
                meta["page_end"] = pe or meta["page_end"]
                # 移除页码标记
                sub = _PAGE_MARKER_RE.sub("", sub).strip()
                if sub:
                    result.append({"text": sub, "metadata": meta})

        # 后处理：合并相邻短节段 & 过滤过小块
        result = self._postprocess(result)
        # 重新编号 + 合并后重新提取页码范围
        for i, r in enumerate(result):
            r["metadata"]["chunk_index"] = i
            # 清理残留标记
            r["text"] = _PAGE_MARKER_RE.sub("", r["text"]).strip()
            ps, pe = self._extract_page_range(r["text"])
            if ps:
                r["metadata"]["page_start"] = ps
            if pe:
                r["metadata"]["page_end"] = pe

        return result

    # ── 页码标记 ──

    def _inject_page_markers(self, text: str, page_starts: list[int]) -> str:
        """在文本中注入 [[PAGE:N]] 标记（用于后续追踪页码）。

        标记放在每页边界处，用双换行包围以确保预处理后独立存在。
        """
        if not page_starts or len(page_starts) <= 1:
            return text

        # 从后往前插入，避免偏移量变化
        chars = list(text)
        for page_num in range(len(page_starts) - 1, 0, -1):
            pos = page_starts[page_num]
            if pos < len(chars):
                marker = f"\n\n[[PAGE:{page_num + 1}]]\n\n"
                for ch in reversed(marker):
                    chars.insert(pos, ch)

        return "".join(chars)

    @staticmethod
    def _extract_page_range(text: str) -> tuple:
        """从文本中提取页码范围。返回 (start_page, end_page) 或 (None, None)。"""
        matches = _PAGE_MARKER_RE.findall(text)
        if not matches:
            return None, None
        pages = sorted(set(int(m) for m in matches))
        return pages[0], pages[-1]

    # ── 章节信息提取 ──

    # 中文数字映射
    _CN_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
                  "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

    @classmethod
    def _parse_cn_number(cls, s: str) -> int:
        """将中文数字转换为整数（如 '十二' → 12, '三' → 3）。"""
        s = s.strip()
        if s.isdigit():
            return int(s)
        if s in cls._CN_DIGITS:
            return cls._CN_DIGITS[s]
        if s.startswith("十"):
            return 10 + cls._CN_DIGITS.get(s[1:], 0)
        if s.endswith("十"):
            return cls._CN_DIGITS.get(s[:-1], 0) * 10
        if "十" in s:
            parts = s.split("十", 1)
            tens = cls._CN_DIGITS.get(parts[0], 0) * 10
            ones = cls._CN_DIGITS.get(parts[1], 0)
            return tens + ones
        return None

    @classmethod
    def _extract_section_info(cls, label: str) -> dict:
        """从章节标签中提取结构化信息。

        Returns:
            {title, chapter, section, part} — chapter/section/part 为 int/str 或 None
        """
        info = {"title": label.strip(), "chapter": None, "section": None, "part": None}

        # Chinese: "第3章 航空器适航" / "第十二章"
        m = re.match(r"第([一二三四五六七八九十\d]+)章", label)
        if m:
            cn = cls._parse_cn_number(m.group(1))
            if cn is not None:
                info["chapter"] = cn
                return info

        # Chinese: "第2.3节"
        m = re.match(r"第([一二三四五六七八九十\d]+(?:\.\d+)?)节", label)
        if m:
            info["section"] = m.group(1)
            return info

        # Chinese: "第二部分"
        m = re.match(r"第([一二三四五六七八九十\d]+)部分", label)
        if m:
            cn = cls._parse_cn_number(m.group(1))
            if cn is not None:
                info["part"] = cn
                return info

        # "Chapter 5" / "CHAPTER 12"
        m = re.match(r"(?i)chapter\s+(\d+)", label)
        if m:
            info["chapter"] = int(m.group(1))
            return info

        # "Section 3.1" / "SECTION 2"
        m = re.match(r"(?i)section\s+(\d+(?:\.\d+)?)", label)
        if m:
            info["section"] = m.group(1)
            return info

        # "Part 2" / "PART A"
        m = re.match(r"(?i)part\s+(\d+|[A-Z]+)", label)
        if m:
            val = m.group(1)
            info["part"] = int(val) if val.isdigit() else val
            return info

        # "3.1.2 System Overview" → chapter=3, section="3.1"
        m = re.match(r"(\d+)\.(\d+(?:\.\d+)?)\s", label)
        if m:
            info["chapter"] = int(m.group(1))
            info["section"] = m.group(2)
            return info

        # Pure number (possibly from heading match)
        m = re.match(r"^(\d+)$", label.strip())
        if m:
            info["chapter"] = int(m.group(1))
            return info

        return info

    # ── 预处理 ──

    def _preprocess_text(self, text: str) -> str:
        """修复 PDF 提取产生的断行，规范化空白。"""
        # 1. 将行内换行（非段落边界）合并 — 上一行不以句末标点结尾时合并
        lines = text.split("\n")
        merged = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                merged.append("")  # 保留空行作为段落分隔
                continue
            if merged and merged[-1] and not re.search(r"[。！？.!?：:—\-,\s]$", merged[-1]):
                # 上一行不以句末标点/连接符结尾 → 合并
                # 如果两行都是英文内容（无 CJK），中间加空格防止粘连
                prev_is_ascii = not re.search(r'[一-鿿]', merged[-1][-20:])
                cur_is_ascii = not re.search(r'[一-鿿]', stripped[:20])
                sep = " " if (prev_is_ascii and cur_is_ascii) else ""
                merged[-1] = merged[-1] + sep + stripped
            else:
                merged.append(stripped)
        text = "\n".join(merged)

        # 2. 规范化空白：3+ 连续换行 → 2 换行，去行尾空格
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)

        return text.strip()

    # ── 章节检测 ──

    def _detect_sections(self, text: str) -> list[tuple[str, str]]:
        """检测文档章节边界，返回 [(label, section_text), ...]。

        按优先级尝试：ATA 验证匹配 → 通用标题 → 双换行段落
        """
        # 策略 1: ATA 章节（含验证）
        ata_sections = self._split_by_ata(text)
        if len(ata_sections) > 1:
            return ata_sections

        # 策略 2: 通用标题模式
        heading_sections = self._split_by_headings(text)
        if len(heading_sections) > 1:
            return heading_sections

        # 策略 3: 双换行段落（当段落足够大时拆分）
        if "\n\n" in text:
            paras = text.split("\n\n")
            # 只有当分段能产生有意义的大段时才用
            avg_len = sum(len(p) for p in paras) / max(len(paras), 1)
            if avg_len > 200 and len(paras) >= 3:
                # 合并相邻短段
                merged_paras = []
                buf = ""
                for p in paras:
                    p = p.strip()
                    if not p:
                        continue
                    if buf and (len(buf) < 200 or len(p) < 200):
                        buf += "\n\n" + p
                    elif buf:
                        merged_paras.append(buf)
                        buf = p
                    else:
                        buf = p
                if buf:
                    merged_paras.append(buf)
                return [(self._label_from_text(p, i), p) for i, p in enumerate(merged_paras)]

        # 无结构 — 整篇作为一个节
        return [(text[:50][:40] or "FULL", text)]

    # ── ATA 章节切分（验证版） ──

    def _split_by_ata(self, text: str) -> list[tuple[str, str]]:
        """按 ATA 章节切分，仅匹配有效模式且出现在行首/标题位置。

        匹配规则（按严格度降序）：
        1. 行首带前缀的完整 ATA 子章节: "ATA 32-41-03", "CHAPTER 32-41"
        2. 行首带前缀的两码章: "ATA 32", "Chapter 72"
        3. 行首裸子章节号(前两码有效): "32-41-03" (仅当独立成行/段首)
        关键约束：必须出现在行首位置（允许前导空白或编号标记），
        不在正文内联匹配。同时过滤过短的目录/索引条目。
        """
        # 行首模式（^ 配合 re.MULTILINE，允许前导空白和列表标记）
        opt_prefix = r"(?:ATA\s+|CHAPTER\s+|CH\.?\s*)?"
        line_start = r"^[\s•·▪\-–—]*"

        # 规则 1+3: 完整 6 位子章节号（行首）
        pattern_full = re.compile(
            line_start + opt_prefix + r"(\d{2})[-.](\d{2})[-.](\d{2})\b",
            re.MULTILINE | re.IGNORECASE,
        )
        # 规则 2: 带强制前缀的两码章节（行首）
        pattern_chapter = re.compile(
            line_start + r"(?:ATA|CHAPTER|CH\.?)\s+(\d{2})\b",
            re.MULTILINE | re.IGNORECASE,
        )

        candidates = []

        for m in pattern_full.finditer(text):
            prefix = m.group(1)
            if prefix in _VALID_ATA_PREFIXES:
                code = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
                candidates.append((m.start(), code, 1))

        for m in pattern_chapter.finditer(text):
            code = m.group(1)
            if code in _VALID_ATA_PREFIXES:
                overlap = any(abs(m.start() - c[0]) < 10 for c in candidates)
                if not overlap:
                    candidates.append((m.start(), code, 2))

        if len(candidates) < 2:
            return [(text[:50][:30] or "GENERAL", text)]

        # 按位置排序并构建节段
        candidates.sort(key=lambda x: x[0])

        result = []
        for i, (start, code, _) in enumerate(candidates):
            next_start = candidates[i + 1][0] if i + 1 < len(candidates) else len(text)
            section_text = text[start:next_start].strip()
            # 过滤目录/索引条目：节段过短（< 500 chars）说明只是引用而非正文
            if len(section_text) >= 500:
                result.append((code, section_text))

        # 如果过滤后只剩 ≤1 节 → 当作无结构化处理
        if len(result) <= 1:
            return [(text[:50][:30] or "GENERAL", text)]

        # 需要至少 3 个不同的 ATA 标签才确认为 ATA 结构化文档
        # 避免把只有 1-2 个巧合数字匹配的非 ATA 文档（如 FAA 手册）错误拆分
        distinct_labels = set(code for code, _ in result if code != "PREAMBLE")
        if len(distinct_labels) < 3:
            return [(text[:50][:30] or "GENERAL", text)]

        # 匹配前的导言文本
        first_start = candidates[0][0]
        if first_start > 0:
            prefix = text[:first_start].strip()
            if len(prefix) > 50:
                result.insert(0, ("PREAMBLE", prefix))

        return result

    # ── 通用标题切分 ──

    def _split_by_headings(self, text: str) -> list[tuple[str, str]]:
        """按通用文档标题模式切分：Chapter/Section/Part/编号标题。"""
        patterns = [
            # "Chapter 5", "CHAPTER 5"
            r"^(?:CHAPTER|Chapter)\s+\d+\b",
            # "Section 3.1", "SECTION 3"
            r"^(?:SECTION|Section)\s+\d+(?:\.\d+)?\b",
            # "Part 2", "PART TWO"
            r"^(?:PART|Part)\s+(\d+|[A-Z]+)\b",
            # Chinese: "第1章", "第2.3节", "第一部分"
            r"^第[一二三四五六七八九十\d]+章",
            r"^第[一二三四五六七八九十\d]+(?:\.\d+)?节",
            r"^第[一二三四五六七八九十\d]+部分",
            # "5. System Description", "3.1.2 Overview"
            r"^\d+(?:\.\d+){1,2}\s+[A-Z一-鿿]",
            # 全大写短行（≤80 字符）：可能是标题
            r"^[A-Z][A-Z\s/-]{8,80}$",
        ]

        all_matches = []
        for pattern in patterns:
            for m in re.finditer(pattern, text, re.MULTILINE):
                all_matches.append((m.start(), m.group().strip()))

        if len(all_matches) < 2:
            return [(text[:50][:40] or "GENERAL", text)]

        all_matches.sort(key=lambda x: x[0])

        result = []
        for i, (pos, label) in enumerate(all_matches):
            next_pos = all_matches[i + 1][0] if i + 1 < len(all_matches) else len(text)
            section_text = text[pos:next_pos].strip()
            if len(section_text) > 30:
                result.append((label[:60], section_text))

        if all_matches and all_matches[0][0] > 0:
            prefix = text[:all_matches[0][0]].strip()
            if len(prefix) > 50:
                result.insert(0, ("PREAMBLE", prefix))

        return result if len(result) > 1 else [(text[:50][:40] or "GENERAL", text)]

    # ── Token 感知分块 ──

    def _chunk_text(self, text: str) -> list[str]:
        """按 token 数量分块，尊重句子边界 + CJK 友好的 token 估计。

        BGE-m3 使用 XLM-RoBERTa tokenizer，中文 ~1.8 tokens/char，
        英文 ~1.3 tokens/word。保守估算：len(text) * 0.55 ≈ tokens。
        """
        max_chars = int(self.chunk_size / 0.55)
        overlap_chars = int(self.chunk_overlap / 0.55)

        # 在句子边界切分（中文 + 英文标点 + 换行）
        sentences = re.split(r"(?<=[。！？.!?\n])\s*", text)
        sentences = [s.strip() for s in sentences if s.strip()]
        if not sentences:
            return [text] if text.strip() else []

        chunks = []
        current = []
        current_len = 0

        for sent in sentences:
            sent_len = len(sent)

            # 单个句子过长 → 强制在 max_chars 处切断
            if sent_len > max_chars:
                # 先刷新当前 chunk
                if current:
                    chunks.append(" ".join(current))
                    current = []
                    current_len = 0
                # 长句按字符数硬切
                for j in range(0, sent_len, max_chars - overlap_chars):
                    piece = sent[j:j + max_chars]
                    if len(piece) >= self.min_chunk_chars:
                        chunks.append(piece)
                continue

            if current_len + sent_len > max_chars and current:
                chunks.append(" ".join(current))
                # 重叠：取上一 chunk 末尾若干句子
                prev = current
                current = []
                overlap_len = 0
                for s in reversed(prev):
                    overlap_len += len(s)
                    current.insert(0, s)
                    if overlap_len >= overlap_chars:
                        break
                current_len = overlap_len

            current.append(sent)
            current_len += sent_len

        if current:
            chunks.append(" ".join(current))

        return chunks if chunks else [text]

    # ── 后处理 ──

    def _postprocess(self, chunks: list[dict]) -> list[dict]:
        """后处理：合并相邻短节段 + 过滤过小块。"""
        if not chunks:
            return []

        # 过滤过小块
        filtered = [c for c in chunks if len(c["text"]) >= self.min_chunk_chars]
        if len(filtered) < 2:
            return filtered

        # 合并相邻短节段
        max_merge_chars = int(self.chunk_size / 0.55 * 1.3)
        short_threshold = self.min_chunk_chars * 3
        merged = []
        i = 0
        while i < len(filtered):
            current = filtered[i]
            combined_text = current["text"]
            # 跟踪合并后的页码范围
            pg_min = current["metadata"].get("page_start", 1)
            pg_max = current["metadata"].get("page_end", 1)
            j = i + 1
            while j < len(filtered):
                nxt = filtered[j]
                if len(nxt["text"]) >= short_threshold:
                    break
                if (current["metadata"].get("ata_chapter") == nxt["metadata"].get("ata_chapter")
                        and len(combined_text) + len(nxt["text"]) <= max_merge_chars):
                    combined_text += "\n\n" + nxt["text"]
                    # 扩展页码范围
                    nxt_pg_s = nxt["metadata"].get("page_start", pg_max)
                    nxt_pg_e = nxt["metadata"].get("page_end", pg_max)
                    pg_min = min(pg_min, nxt_pg_s) if nxt_pg_s else pg_min
                    pg_max = max(pg_max, nxt_pg_e) if nxt_pg_e else pg_max
                    j += 1
                else:
                    break
            if j > i + 1:
                current = dict(current)
                current["text"] = combined_text
                current["metadata"] = dict(current["metadata"])
                current["metadata"]["page_start"] = pg_min
                current["metadata"]["page_end"] = pg_max
                merged.append(current)
                i = j
            else:
                merged.append(current)
                i += 1

        return merged

    # ── 辅助 ──

    @staticmethod
    def _is_ata_label(label: str) -> bool:
        """判断节段标签是否为有效 ATA 编号。"""
        return bool(re.match(r"^\d{2}(-\d{2}(-\d{2})?)?$", label)
                    and label[:2] in _VALID_ATA_PREFIXES)

    @staticmethod
    def _label_from_text(text: str, index: int) -> str:
        """从文本片段生成节段标签。"""
        first_line = text.strip().split("\n")[0][:60]
        return first_line if first_line else f"SEC{index + 1}"
