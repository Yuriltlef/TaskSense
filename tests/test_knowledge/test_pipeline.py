"""知识库流水线测试."""

import pytest

from app.knowledge.pipeline import KnowledgePipeline


class TestKnowledgePipeline:
    @pytest.fixture
    def pipeline(self):
        return KnowledgePipeline()

    def test_init(self, pipeline):
        assert pipeline.loader is not None
        assert pipeline.embedder is not None
        assert pipeline.store is not None
        assert pipeline.retriever is not None

    def test_get_stats(self, pipeline):
        stats = pipeline.get_stats()
        assert "total_files" in stats
        assert "chunks_stored" in stats

    def test_search_empty(self, pipeline):
        results = pipeline.search("landing gear")
        # 知识库可能为空或已有数据
        assert isinstance(results, list)


class TestAgentOrchestrator:
    def test_init(self):
        from app.agent.orchestrator import AgentOrchestrator
        a = AgentOrchestrator()
        assert a is not None

    def test_ask(self):
        from app.agent.orchestrator import agent
        result = agent.ask("landing gear maintenance")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_generate_daily_report(self):
        from app.agent.orchestrator import agent
        report = agent.generate_daily_report()
        assert "航空维护每日报告" in report
        assert "机队状态" in report or "AOG" in report

    def test_guess_ata(self):
        from app.agent.orchestrator import agent
        assert agent._guess_ata("起落架异响") == "32"
        assert agent._guess_ata("发动机振动") == "72"
        assert agent._guess_ata("landing gear issue") == "32"
        assert agent._guess_ata("unknown thing") == ""

    def test_compliance_check(self):
        from app.agent.orchestrator import agent
        from app.core.state import state

        t = state.create_task(
            title="Test Compliance",
            aircraft_reg="B-5823",
            ata_chapter="32-41-03",
        )
        result = agent.check_compliance(t.id)
        assert "is_compliant" in result
        assert "warnings" in result
