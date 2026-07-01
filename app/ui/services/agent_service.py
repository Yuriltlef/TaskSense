"""Agent 服务 — UI 层的 Agent 调用桥梁。支持会话上下文。"""

from app.agent.orchestrator import agent


class AgentService:
    """面向 UI 的 Agent 服务封装。

    支持多轮对话：通过 session_id 保持上下文。
    """

    @staticmethod
    def ask(question: str, session_id: str = "default", strict: bool = False,
            cancel_event=None) -> str:
        """向 Agent 提问（保持对话上下文）。"""
        return agent.ask(question, session_id, strict=strict, cancel_event=cancel_event)

    @staticmethod
    def clear_session(session_id: str = "default"):
        """清除指定会话的对话历史。"""
        agent.clear_conversation(session_id)

    @staticmethod
    def get_conversation_summary(session_id: str = "default") -> str:
        """获取会话摘要（调试用）。"""
        conv = agent.get_conversation(session_id)
        return conv.get_history_summary()

    @staticmethod
    def get_suggestions(task_description: str) -> dict:
        return agent.suggest_task_template(task_description)

    @staticmethod
    def check_compliance(task_id: str) -> dict:
        return agent.check_compliance(task_id)

    @staticmethod
    def get_daily_report() -> str:
        return agent.generate_daily_report()

    @staticmethod
    def get_board_summary() -> str:
        from app.agent.tools.board_tools import get_board_summary
        return get_board_summary.invoke({})

    @staticmethod
    def search_knowledge(query: str) -> str:
        from app.agent.tools.search_tools import search_knowledge_base
        return search_knowledge_base.invoke({"query": query})
