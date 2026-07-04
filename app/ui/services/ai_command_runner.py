# -*- coding: utf-8 -*-
"""AI 命令执行器 — 消除 7 个 _cmd_* 方法中重复的 guard + setup + cancel 样板。"""

from app.agent.active_task import active_task_registry
from app.ui.widgets.toast import Toast


class AICommandRunner:
    """AI 命令通用执行器。

    用法：
        runner = AICommandRunner(board_page)
        if not runner.ensure_ready(): return
        runner.setup("生成任务", "gen_tasks")
        # ... 启动后台线程，用 runner.get_cancel() 获取取消事件 ...
    """

    def __init__(self, board_page):
        self._bp = board_page

    # ── 公开 API ──

    def ensure_ready(self) -> bool:
        """检查 AI 面板是否可用。不可用时显示 Toast 并返回 False。"""
        if not self._bp.ai_chat:
            Toast.show(self._bp._page, "AI 面板未就绪", "warning")
            return False
        if self._bp.ai_chat.is_task_running:
            Toast.show(self._bp._page, "AI 正在处理中，请等待当前任务完成", "warning")
            return False
        return True

    def setup(self, label: str, session_id: str,
              task_type: str = "ai_panel",
              initial_status: str = "准备中..."):
        """AI 命令通用准备：打开面板 + 任务卡片 + 注册 + 状态栏。"""
        if task_type == "ai_panel":
            self._bp._open_ai_panel()
            self._bp.ai_chat.show_task_card(
                label,
                on_cancel=lambda sid=session_id: self._bp._on_status_task_cancel(sid))
        self._bp._task_registry.register(
            session_id, label, initial_status, task_type)
        active_task_registry.set_active(
            session_id, label, "executing", f"Running: {label}")

    def get_cancel(self):
        """安全获取当前 cancel_event（可能为 None）。"""
        return getattr(self._bp.ai_chat, '_cancel_event', None) \
            if self._bp.ai_chat else None
