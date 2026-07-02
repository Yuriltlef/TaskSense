# -*- coding: utf-8 -*-
"""AI 幽灵任务卡片 — 半透明预览 + 接受/拒绝按钮。

架构：
- AIProposal: 数据类，描述一条 AI 建议
- AIGhostCard: 半透明卡片组件，内嵌接受/拒绝按钮
- GhostCardManager: 管理当前看板上的所有幽灵卡片，支持批量操作
"""

import flet as ft
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Callable

from app.config.theme import theme, s
from app.core.events import event_bus, AppEvent, EventType


@dataclass
class AIProposal:
    """一条 AI 建议（幽灵任务或修改建议）。"""

    id: str
    proposal_type: str  # "new_task" | "classify" | "schedule" | "acceptance"
    task_data: dict = field(default_factory=dict)
    source_column: str = ""
    target_column: str = ""
    description: str = ""
    created_at: datetime = field(default_factory=datetime.now)


class GhostCardManager:
    """管理看板上所有幽灵卡片的生命周期。

    用法：
        mgr = GhostCardManager()
        mgr.add(proposal, column_id, index)
        mgr.accept_all()  # 批量接受
        mgr.reject_all()  # 批量拒绝
        mgr.count  # 当前幽灵卡片数量
    """

    def __init__(self):
        self._ghosts: dict[str, "AIGhostCard"] = {}
        self._by_column: dict[str, list[str]] = {}  # column_id → [proposal_id]

    def add(self, proposal: AIProposal, column_id: str,
            on_accept: Callable = None, on_reject: Callable = None) -> "AIGhostCard":
        """创建幽灵卡片并注册。"""
        ghost = AIGhostCard(proposal, on_accept=on_accept, on_reject=on_reject)
        ghost._mgr = self
        self._ghosts[proposal.id] = ghost
        self._by_column.setdefault(column_id, []).append(proposal.id)
        return ghost

    def remove(self, proposal_id: str):
        """移除幽灵卡片。"""
        self._ghosts.pop(proposal_id, None)
        for ids in self._by_column.values():
            if proposal_id in ids:
                ids.remove(proposal_id)

    def accept_all(self):
        """批量接受所有幽灵卡片。"""
        for ghost in list(self._ghosts.values()):
            ghost._do_accept()

    def reject_all(self):
        """批量拒绝所有幽灵卡片。"""
        for ghost in list(self._ghosts.values()):
            ghost._do_reject()

    @property
    def count(self) -> int:
        return len(self._ghosts)

    def get_for_column(self, column_id: str) -> list["AIGhostCard"]:
        """获取某列的幽灵卡片（按插入顺序）。"""
        ids = self._by_column.get(column_id, [])
        return [self._ghosts[pid] for pid in ids if pid in self._ghosts]


class AIGhostCard(ft.Container):
    """半透明幽灵任务卡片，带接受/拒绝按钮。

    支持三种建议类型：
    - new_task: 创建任务到 backlog
    - classify: 设优先级 + 移动到 triage
    - schedule: 排程 + 移动到 scheduled
    """

    def __init__(
        self,
        proposal: AIProposal,
        on_accept: Callable = None,
        on_reject: Callable = None,
        **_kw,
    ):
        super().__init__(
            width=theme.card_width,
            bgcolor=ft.Colors.TRANSPARENT,
            opacity=0.55,
            border=ft.border.all(1.5, theme.info),
            border_radius=s(10),
            padding=ft.padding.all(s(12)),
        )
        self.proposal = proposal
        self._on_accept = on_accept
        self._on_reject = on_reject
        self._mgr: Optional[GhostCardManager] = None
        self.content = self._build()

    def _build(self):
        ff = theme.font_family
        td = self.proposal.task_data

        title = td.get("title", "AI 建议任务")
        ata = td.get("ata_chapter", "")
        _PRI_LABELS = {"aog": "AOG", "cat_a": "CAT A", "cat_b": "CAT B",
                       "cat_c": "CAT C", "cat_d": "CAT D"}
        priority = td.get("priority", "cat_c")
        ptype = self.proposal.proposal_type

        type_labels = {
            "new_task": "新建任务",
            "classify": "自动分类",
            "schedule": "自动排程",
            "acceptance": "验收建议",
        }
        type_label = type_labels.get(ptype, ptype)

        # 描述行
        detail_parts = []
        if ata:
            detail_parts.append(f"ATA {ata}")
        detail_parts.append(_PRI_LABELS.get(priority, priority.upper()))
        if td.get("employee_name"):
            detail_parts.append(td["employee_name"])
        detail_text = " · ".join(detail_parts)

        return ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.PSYCHOLOGY_OUTLINED, size=s(13), color=theme.info),
                ft.Text(f"AI {type_label}", size=s(10),
                        color=theme.info, font_family=ff, weight=ft.FontWeight.W_600),
                ft.Container(expand=True),
            ], spacing=s(6)),
            ft.Container(height=s(6)),
            ft.Text(title, size=s(12), color=theme.text_primary, font_family=ff,
                    weight=ft.FontWeight.W_500, max_lines=2),
            ft.Container(height=s(4)),
            ft.Text(detail_text, size=s(10), color=theme.text_secondary, font_family=ff),
            ft.Container(height=s(8)),
            ft.Row([
                ft.ElevatedButton("接受",
                    icon=ft.Icons.CHECK,
                    style=ft.ButtonStyle(
                        bgcolor=theme.success, color=ft.Colors.WHITE,
                        shape=ft.RoundedRectangleBorder(radius=s(6)),
                        padding=ft.padding.symmetric(horizontal=s(10), vertical=s(3)),
                        text_style=ft.TextStyle(size=s(10), font_family=ff)),
                    on_click=lambda e: self._do_accept()),
                ft.OutlinedButton("拒绝",
                    icon=ft.Icons.CLOSE,
                    style=ft.ButtonStyle(
                        color=theme.error,
                        side=ft.BorderSide(1, theme.error),
                        shape=ft.RoundedRectangleBorder(radius=s(6)),
                        padding=ft.padding.symmetric(horizontal=s(10), vertical=s(3)),
                        text_style=ft.TextStyle(size=s(10), font_family=ff)),
                    on_click=lambda e: self._do_reject()),
            ], spacing=s(6)),
        ], spacing=0, tight=True)

    def _do_accept(self):
        """接受建议 — 根据 proposal_type 执行对应的业务逻辑。"""
        from app.core.services.task_service import task_service
        from app.core.state import state

        td = self.proposal.task_data
        ptype = self.proposal.proposal_type
        tid = td.get("id", "")  # 已有任务 ID（classify/schedule 场景）

        try:
            if ptype == "new_task":
                # 创建新任务到 backlog
                t = task_service.create_task(
                    title=td.get("title", "AI Task"),
                    description=td.get("description", ""),
                    aircraft_reg=td.get("aircraft_reg", ""),
                    ata_chapter=td.get("ata_chapter", ""),
                    priority=td.get("priority", "cat_c"),
                    task_type=td.get("task_type", "troubleshoot"),
                    zone=td.get("zone", ""),
                    estimated_hours=float(td.get("estimated_hours", 0)),
                    employee_id=td.get("employee_id", ""),
                    employee_name=td.get("employee_name", ""),
                )
                td["id"] = t.id  # 回填 ID

            elif ptype == "classify":
                # 设置优先级并移动到 triage
                if tid:
                    task_service.set_priority(tid, td.get("priority", "cat_c"))
                    task_service.move_task(tid, "triage", changed_by="ai_agent")

            elif ptype == "schedule":
                # 设置时间/人员并移动到 scheduled
                if tid:
                    from datetime import datetime as dt
                    updates = {}
                    if td.get("planned_start"):
                        try:
                            updates["planned_start"] = dt.strptime(
                                td["planned_start"], "%Y-%m-%d %H:%M")
                        except ValueError:
                            pass
                    if td.get("planned_end"):
                        try:
                            updates["planned_end"] = dt.strptime(
                                td["planned_end"], "%Y-%m-%d %H:%M")
                        except ValueError:
                            pass
                    if td.get("employee_id"):
                        updates["employee_id"] = td["employee_id"]
                    if td.get("employee_name"):
                        updates["employee_name"] = td["employee_name"]
                        updates["assignee"] = td["employee_name"]
                    if td.get("estimated_hours"):
                        updates["estimated_hours"] = float(td["estimated_hours"])
                    if updates:
                        task_service.update_task(tid, **updates)
                    task_service.move_task(tid, "scheduled", changed_by="ai_agent")

            # 通知
            from app.core.services.log_service import log_service
            from app.core.models.log_entry import LogType
            log_service.log(
                LogType.SYSTEM_AUTO, task_id=tid or "",
                task_title=td.get("title", ""),
                user="ai_agent",
                description=f"AI 建议已接受: {ptype}",
            )
            event_bus.emit(AppEvent(
                type=EventType.AI_PROPOSAL_ACCEPTED,
                data={"proposal_id": self.proposal.id, "type": ptype, "task_id": tid},
            ))
        except Exception as ex:
            print(f"[AIGhostCard] accept failed: {ex}")

        if self._on_accept:
            self._on_accept(self.proposal)
        if self._mgr:
            self._mgr.remove(self.proposal.id)
        self._remove_self()

    def _do_reject(self):
        """拒绝建议 — 仅记录事件，不执行任何操作。"""
        event_bus.emit(AppEvent(
            type=EventType.AI_PROPOSAL_REJECTED,
            data={"proposal_id": self.proposal.id},
        ))
        if self._on_reject:
            self._on_reject(self.proposal)
        if self._mgr:
            self._mgr.remove(self.proposal.id)
        self._remove_self()

    def _remove_self(self):
        """从父容器中安全移除此卡片。"""
        try:
            parent = self.parent
            if parent is not None:
                if isinstance(parent, ft.Column):
                    if self in parent.controls:
                        parent.controls.remove(self)
                        parent.update()
                elif hasattr(parent, 'controls') and self in parent.controls:
                    parent.controls.remove(self)
                    parent.update()
        except Exception:
            pass
