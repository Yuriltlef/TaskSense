"""Agent 知识库问答能力测试."""

import pytest

from app.agent.orchestrator import agent
from app.knowledge.pipeline import KnowledgePipeline


class TestKnowledgeBaseReady:
    """验证知识库已构建且可检索（需已构建 KB + --run-slow）。"""

    @pytest.fixture(autouse=True)
    def pipeline(self):
        return KnowledgePipeline()

    @pytest.mark.needs_kb
    def test_kb_has_chunks(self, pipeline):
        """知识库已有数据。"""
        stats = pipeline.get_stats()
        assert stats["total"] > 0, (
            "知识库为空，请先运行: python scripts/build_kb.py embed"
        )

    @pytest.mark.slow
    @pytest.mark.needs_kb
    def test_search_returns_results(self, pipeline):
        """搜索返回结果（需加载嵌入模型）。"""
        results = pipeline.search("maintenance", top_k=3)
        assert len(results) > 0
        for r in results:
            assert "text" in r
            assert "metadata" in r
            assert "score" in r
            assert r["score"] >= 0

    @pytest.mark.slow
    @pytest.mark.needs_kb
    def test_search_ata_specific(self, pipeline):
        """按 ATA 章节搜索（需加载嵌入模型）。"""
        results = pipeline.search("landing gear", top_k=5)
        assert len(results) > 0
        found = any("gear" in r["text"].lower() or "landing" in r["text"].lower()
                    for r in results)
        assert found, "搜索结果应包含 landing gear 相关内容"


class TestAgentQuestionAnswering:
    """Agent 问答能力（需已构建 KB + --run-slow）。"""

    @pytest.mark.slow
    @pytest.mark.needs_kb
    def test_ask_returns_string(self):
        result = agent.ask("aircraft maintenance")
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.slow
    @pytest.mark.needs_kb
    def test_ask_with_kb_content(self):
        """问一个知识库中有答案的问题。"""
        result = agent.ask("landing gear maintenance procedure")
        assert len(result) > 50, "回答不应太短"
        assert "未找到" not in result or "结果" in result

    @pytest.mark.slow
    @pytest.mark.needs_kb
    def test_ask_chinese(self):
        """中文查询。"""
        result = agent.ask("起落架维护")
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.slow
    @pytest.mark.needs_kb
    def test_ask_unknown_topic(self):
        """查询知识库中没有的内容。"""
        result = agent.ask("xyzzy_nonexistent_topic_12345")
        assert isinstance(result, str)
        assert len(result) > 0


class TestAgentReportGeneration:
    """Agent 报告生成。"""

    def test_daily_report(self):
        report = agent.generate_daily_report()
        assert isinstance(report, str)
        assert len(report) > 0
        assert "航空维护每日报告" in report

    def test_report_contains_sections(self):
        report = agent.generate_daily_report()
        sections = ["机队状态", "任务概况"]
        for sec in sections:
            assert sec in report, f"报告应包含 '{sec}'"


class TestAgentTaskSuggestion:
    """Agent 任务模板建议。"""

    def test_suggest_basic(self):
        result = agent.suggest_task_template("起落架异响排查")
        assert isinstance(result, dict)
        assert "ata_chapter" in result
        assert "task_type" in result
        assert "priority" in result

    def test_suggest_ata_guess(self):
        """验证 ATA 推测能力。"""
        # 中文关键词 → ATA 章节
        assert agent._guess_ata("起落架") == "32"
        assert agent._guess_ata("发动机") == "72"
        assert agent._guess_ata("燃油泵") == "28"
        assert agent._guess_ata("APU故障") == "49"

    def test_suggest_ata_guess_english(self):
        assert agent._guess_ata("landing gear issue") == "32"
        assert agent._guess_ata("engine vibration") == "72"
        assert agent._guess_ata("hydraulic leak") == "29"
        assert agent._guess_ata("wing damage") == "57"

    def test_suggest_unknown(self):
        """未知关键词返回空字符串。"""
        assert agent._guess_ata("xyzzy_unknown") == ""


class TestAgentComplianceCheck:
    """Agent 合规检查。"""

    def test_check_basic(self):
        from app.core.state import state
        t = state.create_task(
            title="Test Compliance Check",
            aircraft_reg="B-TEST",
            ata_chapter="32-41-03",
        )
        result = agent.check_compliance(t.id)
        assert isinstance(result, dict)
        assert "is_compliant" in result
        assert "warnings" in result
        assert "task_title" in result

    def test_check_missing_fields(self):
        """缺少必要字段时应报警告。"""
        from app.core.state import state
        t = state.create_task(title="Incomplete Task")
        result = agent.check_compliance(t.id)
        assert not result["is_compliant"]
        assert len(result["warnings"]) >= 1

    def test_check_rii_requires_inspector(self):
        """RII 任务需要检查员。"""
        from app.core.state import state
        t = state.create_task(
            title="RII Task",
            aircraft_reg="B-RII",
            is_rii=True,
        )
        result = agent.check_compliance(t.id)
        warns = [w for w in result["warnings"] if "RII" in w or "检查员" in w]
        assert len(warns) >= 1


class TestAgentTools:
    """Agent 工具函数测试。"""

    def test_get_board_summary(self):
        from app.agent.tools.board_tools import get_board_summary
        result = get_board_summary.invoke({})
        assert isinstance(result, str)
        assert "看板摘要" in result

    def test_get_task_detail(self):
        from app.agent.tools.board_tools import get_task_detail
        from app.core.state import state
        t = state.create_task(
            title="Tool Test Task",
            aircraft_reg="B-TOOL",
            ata_chapter="27-10-00",
        )
        result = get_task_detail.invoke({"task_id": t.id})
        assert t.title in result
        assert t.aircraft_reg in result

    def test_search_related_tasks(self):
        from app.agent.tools.board_tools import search_related_tasks
        from app.core.state import state
        # 确保有相关任务
        state.create_task(title="Landing Gear A", ata_chapter="32-41-03")
        state.create_task(title="Landing Gear B", ata_chapter="32-31-01")
        result = search_related_tasks.invoke({"ata_chapter": "32"})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_search_knowledge_base(self):
        from app.agent.tools.search_tools import search_knowledge_base
        result = search_knowledge_base.invoke(
            {"query": "aircraft maintenance standard", "top_k": 3}
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_lookup_ata(self):
        from app.agent.tools.search_tools import lookup_ata_chapter
        result = lookup_ata_chapter.invoke({"ata_code": "32"})
        assert isinstance(result, str)
        assert len(result) > 0
