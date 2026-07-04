# -*- coding: utf-8 -*-
"""取消协调器 — 统一处理 AI 任务取消时的幽灵卡片清除。

被 board_page._on_status_task_cancel 调用。
"""

from app.core.logging import log
from app.core.state import state


class CancelCoordinator:
    """取消 AI 任务时清理幽灵卡片标记。

    支持两种模式：
    - 单任务：只清除指定任务的 ai_proposed 及相关标记
    - 批量：清除所有 ai_proposed 任务的标记
    """

    @staticmethod
    def clear_ghost(task_id: str = "") -> list[str]:
        """清除幽灵卡片标记。

        如果 task_id 以 classify_/schedule_/review_ 开头，
        提取真实 task_id 并只清除该任务。
        否则清除全部 ai_proposed 任务。

        返回受影响的真实 task_id 列表。
        """
        # 单任务模式：提取真实 task_id
        for prefix in ("classify_", "schedule_", "review_"):
            if task_id.startswith(prefix):
                real_tid = task_id[len(prefix):]
                if real_tid:
                    log.info("cancel.clear_ghost", task_id=real_tid, mode="single")
                    CancelCoordinator._clear_one(real_tid)
                    return [real_tid]
                return []

        # 批量模式：清除全部
        affected = []
        for t in state.get_all_tasks():
            if t.ai_proposed:
                try:
                    state.update_task(t.id, ai_proposed=False,
                                      ai_priority=None,
                                      ai_acceptance_recommendation=None,
                                      ai_acceptance_reason=None)
                    affected.append(t.id)
                except Exception:
                    pass
        return affected

    @staticmethod
    def _clear_one(task_id: str):
        """清除单个任务的幽灵标记。"""
        t = state.get_task(task_id)
        if not t or not t.ai_proposed:
            return

        updates: dict = {"ai_proposed": False}
        if t.ai_priority:
            updates["ai_priority"] = None
        if t.ai_acceptance_recommendation:
            updates["ai_acceptance_recommendation"] = None
            updates["ai_acceptance_reason"] = None
        if t.ai_suggestions:
            cleaned = [s for s in t.ai_suggestions
                       if not (isinstance(s, dict) and
                               s.get("proposal_type") in ("schedule",))]
            if len(cleaned) != len(t.ai_suggestions):
                updates["ai_suggestions"] = cleaned

        try:
            state.update_task(task_id, **updates)
        except Exception:
            pass
