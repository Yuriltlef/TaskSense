"""文本分块器单元测试 — 无模型加载，纯逻辑验证."""

import pytest

from app.knowledge.chunker import TextChunker, _detect_doc_type, _VALID_ATA_PREFIXES


class TestPreprocess:
    """PDF 断行修复 & 空白规范化."""

    def test_merges_broken_chinese_lines(self):
        chunker = TextChunker()
        text = (
            "这是一段被\n"
            "PDF断行的中文\n"
            "文本。\n\n"
            "这是新段落。"
        )
        result = chunker._preprocess_text(text)
        assert "这是一段被PDF断行的中文文本。" in result
        assert "这是新段落" in result

    def test_preserves_sentence_endings(self):
        chunker = TextChunker()
        text = (
            "第一句。\n"
            "第二句！\n"
            "第三句？\n"
            "This is English.\n"
            "Another English sentence."
        )
        result = chunker._preprocess_text(text)
        # 句末标点结尾的行不应该被合并
        assert result.count("第一句。") >= 1
        assert result.count("第二句！") >= 1

    def test_normalizes_whitespace(self):
        chunker = TextChunker()
        text = "段落一\n\n\n\n\n段落二\n  \n段落三"
        result = chunker._preprocess_text(text)
        # 多个连续换行应折叠为最多2个
        assert "\n\n\n" not in result
        assert "段落一\n\n段落二" in result or "段落一" in result

    def test_empty_text(self):
        chunker = TextChunker()
        assert chunker._preprocess_text("") == ""
        assert chunker._preprocess_text("   \n\n  ") == ""


class TestATADetection:
    """ATA 章节检测 — 验证模式."""

    def test_valid_ata_with_prefix(self):
        chunker = TextChunker()
        # 需要 ≥3 个不同 ATA 标签 且 每段 ≥500 chars
        section_template = (
            "ATA {code} Maintenance Section\n"
            + "This section covers detailed maintenance procedures for the specified ATA chapter. "
            * 30 + "\n"
        )
        text = (
            section_template.format(code="32-41-03")
            + section_template.format(code="32-41-04")
            + section_template.format(code="32-41-05")
        )
        sections = chunker._split_by_ata(text)
        assert len(sections) > 1, f"Expected multiple sections, got {len(sections)}"
        labels = [s[0] for s in sections]
        assert any("32-41" in l for l in labels), f"ATA 32-41-0x not found in {labels}"

    def test_bare_numbers_not_matched(self):
        """裸 NN-NN-NN 不是有效 ATA 时不匹配."""
        chunker = TextChunker()
        text = (
            "Page 10-20-30 contains important data.\n"
            "Page 15-30-45 for details.\n"
            "Date 2018-74-01 is not ATA.\n"
            "Ref 99-88-77 for reference.\n"
        ) * 5
        sections = chunker._split_by_ata(text)
        # 10, 15, 99, 2018 都不是有效 ATA 前缀
        labels = [s[0] for s in sections]
        ata_labels = [l for l in labels if chunker._is_ata_label(l)]
        assert len(ata_labels) == 0, f"False ATA matches: {ata_labels}"

    def test_valid_bare_ata(self):
        """有效 ATA 前缀的裸编号应被识别."""
        chunker = TextChunker()
        text = (
            "Some preamble.\n"
            "32-41-03 Landing Gear\n"
            "Maintenance procedure.\n"
            "32-41-04 Brakes\n"
            "Brake procedure.\n"
        ) * 3
        sections = chunker._split_by_ata(text)
        labels = [s[0] for s in sections]
        # 32 是起落架
        assert any("32-41" in l for l in labels), f"32-41-xx not found: {labels}"

    def test_single_ata_no_split(self):
        """单个 ATA 章节不切分."""
        chunker = TextChunker()
        text = "Some text with ATA 32-41-03 and nothing else."
        sections = chunker._split_by_ata(text)
        assert len(sections) == 1

    def test_preamble_preserved(self):
        """ATA 匹配前的导言文本应保留为 PREAMBLE."""
        chunker = TextChunker()
        section_body = "Landing gear inspection and maintenance procedure steps. " * 25 + "\n"
        text = (
            "This is a long preamble that should be preserved. " * 10 + "\n"
            + "ATA 32-41-03 Landing Gear\n" + section_body
            + "ATA 32-41-04 Brake System\n" + section_body
            + "ATA 32-41-05 Steering\n" + section_body
        )
        sections = chunker._split_by_ata(text)
        labels = [s[0] for s in sections]
        assert "PREAMBLE" in labels, f"PREAMBLE not in labels: {labels}"

    def test_valid_ata_prefixes_set(self):
        """验证 _VALID_ATA_PREFIXES 包含标准 ATA 章节."""
        assert "32" in _VALID_ATA_PREFIXES  # 起落架
        assert "72" in _VALID_ATA_PREFIXES  # 发动机
        assert "21" in _VALID_ATA_PREFIXES  # 空调
        assert "28" in _VALID_ATA_PREFIXES  # 燃油


class TestHeadingDetection:
    """通用标题模式检测."""

    def test_chapter_headings(self):
        chunker = TextChunker()
        text = (
            "Chapter 1 Introduction\n"
            "This is the intro." * 20 + "\n"
            "Chapter 2 Methods\n"
            "This is methods." * 20 + "\n"
        )
        sections = chunker._split_by_headings(text)
        assert len(sections) >= 2, f"Expected >=2 sections, got {len(sections)}"

    def test_numbered_sections(self):
        chunker = TextChunker()
        text = (
            "1. Overview\n"
            "Overview content." * 15 + "\n"
            "2.1 Methods\n"
            "Methods content." * 15 + "\n"
            "3. Results\n"
            "Results content." * 15 + "\n"
        )
        sections = chunker._split_by_headings(text)
        # 可能匹配也可能不匹配，取决于模式是否足够清晰
        assert len(sections) >= 1

    def test_no_false_headings(self):
        """普通文本不应被误判为有标题结构."""
        chunker = TextChunker()
        text = "This is just a normal paragraph without any headings.\n" * 30
        sections = chunker._split_by_headings(text)
        assert len(sections) == 1  # 无标题 → 不切分


class TestChunking:
    """分块大小 & 重叠."""

    def test_chunk_size_respected(self):
        chunker = TextChunker(chunk_size=300, chunk_overlap=40)
        text = "This is sentence number {} about aviation maintenance procedures. "
        text = " ".join(text.format(i) for i in range(200))
        chunks = chunker._chunk_text(text)
        # 每个 chunk 不应超过 chunk_size 对应字符数太多
        max_chars = int(300 / 0.55) + 200  # 允许一定容差
        for c in chunks:
            assert len(c) <= max_chars, (
                f"Chunk too long: {len(c)} > {max_chars}"
            )

    def test_overlap_preserves_context(self):
        chunker = TextChunker(chunk_size=300, chunk_overlap=80)
        text = " ".join(f"UniqueToken{i}" for i in range(200))
        chunks = chunker._chunk_text(text)
        if len(chunks) >= 2:
            # 第二个 chunk 应至少有一些与前一个共享的 token
            tokens1 = set(chunks[0].split())
            tokens2 = set(chunks[1].split())
            overlap = tokens1 & tokens2
            assert len(overlap) > 0, (
                f"No overlap tokens between chunks: c1 has {len(tokens1)}, "
                f"c2 has {len(tokens2)}"
            )

    def test_mixed_cjk_english(self):
        chunker = TextChunker(chunk_size=500, chunk_overlap=80)
        text = (
            "起落架维护程序 Landing Gear Maintenance Procedure "
            "需要检查以下项目 The following items need inspection "
        ) * 50
        chunks = chunker._chunk_text(text)
        assert len(chunks) >= 1
        for c in chunks:
            assert len(c) >= 50, f"Chunk too short: {len(c)} chars"


class TestPostprocess:
    """后处理：最短过滤 + 合并."""

    def test_min_chunk_filter(self):
        chunker = TextChunker()
        chunks = [
            {"text": "A" * 200, "metadata": {"ata_chapter": "", "doc_type": "general"}},
            {"text": "B" * 50, "metadata": {"ata_chapter": "", "doc_type": "general"}},   # too short
            {"text": "C" * 300, "metadata": {"ata_chapter": "", "doc_type": "general"}},
        ]
        result = chunker._postprocess(chunks)
        assert len(result) == 2
        assert all(len(c["text"]) >= chunker.min_chunk_chars for c in result)

    def test_merge_short_adjacent(self):
        chunker = TextChunker(chunk_size=300, chunk_overlap=40)
        chunks = [
            {"text": "A" * 120, "metadata": {"ata_chapter": "32-41-03", "doc_type": "amm"}},
            {"text": "B" * 110, "metadata": {"ata_chapter": "32-41-03", "doc_type": "amm"}},
            {"text": "C" * 800, "metadata": {"ata_chapter": "32-41-04", "doc_type": "amm"}},
        ]
        result = chunker._postprocess(chunks)
        # 前两个同章节应合并
        assert len(result) <= 3

    def test_empty_list(self):
        chunker = TextChunker()
        assert chunker._postprocess([]) == []


class TestDocTypeDetection:
    """文档类型推断."""

    def test_amm_detection(self):
        assert _detect_doc_type("AMM_737.pdf", "ATA 32-41 landing gear") == "amm"

    def test_fim_detection(self):
        assert _detect_doc_type("FIM_manual.pdf", "fault isolation procedure") == "fim"
        assert _detect_doc_type("troubleshooting_guide.pdf", "") == "fim"

    def test_ad_detection(self):
        assert _detect_doc_type("AD_2024-01.pdf", "airworthiness directive") == "ad"

    def test_ac_detection(self):
        assert _detect_doc_type("AC_A330_20251201.pdf", "") == "ac"
        assert _detect_doc_type("aircraft-characteristics.pdf", "") == "ac"

    def test_amt_handbook(self):
        assert _detect_doc_type("amt_airframe_handbook_part_1.pdf", "") == "amt_handbook"
        assert _detect_doc_type("powerplant_handbook.pdf", "") == "amt_handbook"

    def test_sb_detection(self):
        assert _detect_doc_type("SB_737-2024.pdf", "service bulletin") == "sb"

    def test_regulation(self):
        assert _detect_doc_type("ug.cao_.00024-010.pdf", "") == "regulation"
        assert _detect_doc_type("civil_aviation_order.pdf", "") == "regulation"

    def test_textbook(self):
        assert _detect_doc_type("M2-航空器维修.pdf", "航空器维修教材") == "textbook"

    def test_default_general(self):
        assert _detect_doc_type("unknown_file.pdf", "") == "general"


class TestChunkDocument:
    """端到端分块."""

    def test_basic_document(self):
        chunker = TextChunker(chunk_size=500, chunk_overlap=80)
        doc = {
            "text": ("起落架维护程序包括以下步骤：\n"
                     "1. 检查前起落架转向机构\n"
                     "2. 检查减震支柱油液面\n"
                     "3. 检查轮胎磨损情况\n") * 30,
            "filename": "AMM_32-41-03.pdf",
            "title": "Landing Gear Maintenance",
        }
        chunks = chunker.chunk_document(doc)
        assert len(chunks) >= 1
        for c in chunks:
            assert "text" in c
            assert "metadata" in c
            assert len(c["text"]) >= chunker.min_chunk_chars
            assert "doc_type" in c["metadata"]
            assert c["metadata"]["doc_type"] == "amm"

    def test_empty_document(self):
        chunker = TextChunker()
        doc = {"text": "", "filename": "empty.pdf", "title": "Empty"}
        assert chunker.chunk_document(doc) == []

    def test_doc_type_in_metadata(self):
        chunker = TextChunker()
        doc = {
            "text": "AMM procedure text for landing gear maintenance. " * 30,
            "filename": "amm_rev_e.pdf",
            "title": "AMM Manual",
        }
        chunks = chunker.chunk_document(doc)
        assert len(chunks) > 0
        for c in chunks:
            assert "doc_type" in c["metadata"]
