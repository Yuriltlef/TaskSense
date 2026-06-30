"""Agent 服务 — UI 层的 Agent 调用桥梁."""

from app.agent.orchestrator import agent


class AgentService:
    """面向 UI 的 Agent 服务封装。

    提供同步接口，UI 可以直接调用获取结果。
    """

    @staticmethod
    def ask(question: str) -> str:
        """向知识库提问。"""
        return agent.ask(question)

    @staticmethod
    def get_suggestions(task_description: str) -> dict:
        """获取任务建议：ATA 章节、步骤、相似任务。"""
        return agent.suggest_task_template(task_description)

    @staticmethod
    def check_compliance(task_id: str) -> dict:
        """合规检查。"""
        return agent.check_compliance(task_id)

    @staticmethod
    def get_daily_report() -> str:
        """获取每日报告。"""
        return agent.generate_daily_report()

    @staticmethod
    def get_board_summary() -> str:
        """获取看板摘要。"""
        from app.agent.tools.board_tools import get_board_summary
        return get_board_summary.invoke({})

    @staticmethod
    def search_knowledge(query: str) -> str:
        """搜索知识库。"""
        from app.agent.tools.search_tools import search_knowledge_base
        return search_knowledge_base.invoke({"query": query})
