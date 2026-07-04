# -*- coding: utf-8 -*-
"""提案处理器 — 统一所有幽灵卡接受/拒绝逻辑。

消除 board_page.py 和 ai_chat.py 中的三重冗余。
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.core.state import state
from app.core.services.task_service import task_service


@dataclass
class ProposalResult:
    """接受/拒绝操作的结果。"""
    task_id: str
    title: str
    result: str           # "accepted" | "rejected"
    action: str           # "moved" | "cleared" | "deleted" | "none"
    detail: str = ""      # 如 "移至 triage"、"任务已删除"


class ProposalHandler:
    """统一管理幽灵卡提案的接受和拒绝。

    使用方式：
        handler = ProposalHandler()
        result = handler.accept(task_id)
        # → 根据提案类型自动执行移动/清理/删除
    """

    @staticmethod
    def accept(task_id: str) -> ProposalResult:
        """接受一条 AI 提案。根据提案类型执行不同操作：
        - classify: 设优先级 + 移至 triage
        - schedule: 更新排程字段 + 移至 scheduled
        - acceptance: 根据建议移至 completed 或 backlog
        - new_task: 仅清除 ai_proposed 标记
        """
        t = state.get_task(task_id)
        if not t:
            return ProposalResult(task_id, "", "accepted", "none",
                                  "任务不存在")
        title = t.title

        acc_rec = getattr(t, 'ai_acceptance_recommendation', None)
        schedule_data = ProposalHandler._extract_schedule_data(t)

        if acc_rec:
            # 验收提案：根据 AI 建议移动
            target = "completed" if acc_rec == "approve" else "backlog"
            task_service.move_task(task_id, target, changed_by="ai_agent")
            state.update_task(task_id, ai_proposed=False,
                              ai_acceptance_recommendation=None,
                              ai_acceptance_reason=None)
            return ProposalResult(task_id, title, "accepted", "moved",
                                  f"移至 {target}")

        if schedule_data:
            # 排程提案：更新排程信息 + 移至 scheduled
            ProposalHandler._apply_schedule_data(task_id, schedule_data)
            task_service.move_task(task_id, "scheduled", changed_by="ai_agent")
            cleaned = [s for s in (t.ai_suggestions or [])
                       if not (isinstance(s, dict) and
                               s.get("proposal_type") == "schedule")]
            state.update_task(task_id, ai_proposed=False, ai_priority=None,
                              ai_suggestions=cleaned)
            return ProposalResult(task_id, title, "accepted", "moved",
                                  "移至 scheduled")

        if t.ai_priority:
            # 分类提案：设优先级 + 移至 triage
            task_service.set_priority(task_id, t.ai_priority.value)
            task_service.move_task(task_id, "triage", changed_by="ai_agent")
            state.update_task(task_id, ai_proposed=False, ai_priority=None)
            return ProposalResult(task_id, title, "accepted", "moved",
                                  "移至 triage")

        # 新任务提案：仅清除标记
        state.update_task(task_id, ai_proposed=False)
        return ProposalResult(task_id, title, "accepted", "cleared",
                              "标记已清除")

    @staticmethod
    def reject(task_id: str) -> ProposalResult:
        """拒绝一条 AI 提案。
        - 验收提案：只清标记，保留任务
        - 分类/排程提案：清理建议标记，保留任务
        - 新任务提案：删除任务
        """
        t = state.get_task(task_id)
        if not t:
            return ProposalResult(task_id, "", "rejected", "none", "任务不存在")
        title = t.title

        acc_rec = getattr(t, 'ai_acceptance_recommendation', None)
        is_modify = t.ai_priority or any(
            isinstance(s, dict) and s.get("proposal_type") == "schedule"
            for s in (t.ai_suggestions or [])
        )

        if acc_rec:
            state.update_task(task_id, ai_proposed=False,
                              ai_acceptance_recommendation=None,
                              ai_acceptance_reason=None)
            return ProposalResult(task_id, title, "rejected", "cleared",
                                  "验收标记已清除，任务保留")

        if is_modify:
            cleaned = [s for s in (t.ai_suggestions or [])
                       if not (isinstance(s, dict) and
                               s.get("proposal_type") == "schedule")]
            state.update_task(task_id, ai_proposed=False, ai_priority=None,
                              ai_suggestions=cleaned)
            return ProposalResult(task_id, title, "rejected", "cleared",
                                  "建议标记已清除，任务保留")

        state.delete_task(task_id)
        return ProposalResult(task_id, title, "rejected", "deleted",
                              "任务已删除")

    @staticmethod
    def accept_all() -> list[ProposalResult]:
        """批量接受全部幽灵卡提案。"""
        return [ProposalHandler.accept(t.id)
                for t in state.get_all_tasks() if t.ai_proposed]

    @staticmethod
    def reject_all() -> list[ProposalResult]:
        """批量拒绝全部幽灵卡提案。"""
        return [ProposalHandler.reject(t.id)
                for t in state.get_all_tasks() if t.ai_proposed]

    # ── 内部辅助 ──

    @staticmethod
    def _extract_schedule_data(t) -> dict:
        for sug in (t.ai_suggestions or []):
            if isinstance(sug, dict) and sug.get("proposal_type") == "schedule":
                return sug
        return {}

    @staticmethod
    def _apply_schedule_data(task_id: str, schedule_data: dict):
        """将排程数据写入任务字段。"""
        dt = datetime
        if schedule_data.get("planned_start"):
            try:
                state.update_task(task_id,
                    planned_start=dt.strptime(schedule_data["planned_start"],
                                              "%Y-%m-%d %H:%M"))
            except ValueError:
                pass
        if schedule_data.get("planned_end"):
            try:
                state.update_task(task_id,
                    planned_end=dt.strptime(schedule_data["planned_end"],
                                            "%Y-%m-%d %H:%M"))
            except ValueError:
                pass
        if schedule_data.get("employee_id"):
            state.update_task(task_id, employee_id=schedule_data["employee_id"])
        if schedule_data.get("employee_name"):
            state.update_task(task_id, employee_name=schedule_data["employee_name"],
                              assignee=schedule_data["employee_name"])
        if schedule_data.get("estimated_hours"):
            state.update_task(task_id,
                              estimated_hours=float(schedule_data["estimated_hours"]))
