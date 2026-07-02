"""Agent 服务 — UI 层的 Agent 调用桥梁。支持会话上下文。"""

from app.agent.orchestrator import agent, _load_prompt


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

    # ── 7 个 Agent 命令 ──

    @staticmethod
    def generate_outline(user_input: str) -> str:
        """根据用户输入生成维护任务大纲。"""
        prompt = _load_prompt("generate_outline.md")
        return agent.ask(f"{prompt}\n\n用户需求: {user_input}", session_id="outline")

    @staticmethod
    def generate_tasks(outline: str) -> str:
        """从大纲批量创建任务到看板。"""
        prompt = _load_prompt("generate_tasks.md")
        return agent.ask(f"{prompt}\n\n大纲: {outline}", session_id="gen_tasks")

    @staticmethod
    def auto_classify(task_ids: str = "") -> str:
        """AI 自动分类（设置优先级）。task_ids 为逗号分隔的任务 ID。"""
        prompt = _load_prompt("auto_classify.md")
        ids_note = f"\n指定任务 ID: {task_ids}" if task_ids else "\n请处理所有待处理任务。"
        return agent.ask(f"{prompt}{ids_note}", session_id="classify")

    @staticmethod
    def auto_schedule(task_ids: str = "") -> str:
        """AI 自动排程。task_ids 为逗号分隔的任务 ID。"""
        prompt = _load_prompt("auto_schedule.md")
        ids_note = f"\n指定任务 ID: {task_ids}" if task_ids else "\n请处理所有已分类任务。"
        return agent.ask(f"{prompt}{ids_note}", session_id="schedule")

    @staticmethod
    def auto_acceptance(task_ids: str = "") -> str:
        """AI 验收审核建议。task_ids 为逗号分隔的任务 ID。"""
        prompt = _load_prompt("auto_acceptance.md")
        ids_note = f"\n指定任务 ID: {task_ids}" if task_ids else "\n请审核所有验收中的任务。"
        return agent.ask(f"{prompt}{ids_note}", session_id="acceptance")

    @staticmethod
    def generate_report(report_type: str = "daily") -> str:
        """生成维护报告（daily | shift | compliance）。"""
        prompt = _load_prompt("generate_reports.md")
        return agent.ask(
            f"{prompt}\n\n请生成一份 {report_type} 报告。", session_id="report"
        )

    @staticmethod
    def task_review(task_ids: str = "") -> str:
        """AI 合规审核。task_ids 为逗号分隔的任务 ID。"""
        prompt = _load_prompt("task_review.md")
        ids_note = f"\n审核任务 ID: {task_ids}" if task_ids else "\n请审核看板上的所有活跃任务。"
        return agent.ask(f"{prompt}{ids_note}", session_id="review")
