# -*- coding: utf-8 -*-
"""看板渲染器 — 看板数据填充 + 幽灵卡注入 + 列级增量更新。"""

from dataclasses import dataclass

from app.core.services.board_service import board_service
from app.core.state import state


@dataclass
class GhostInfo:
    """幽灵卡渲染信息（消除 _render_ai_ghost_cards / _add_single_ghost / _refresh_board
    中三次重复的类型判断逻辑）。"""
    prop_type: str           # "classify" | "schedule" | "acceptance" | "new_task"
    render_column: str       # 目标列 ID
    source_column: str       # 来源列 ID
    display_priority: str    # 显示用优先级
    task_data: dict          # 传给 AIGhostCard 的任务数据


class BoardRenderer:
    """看板数据渲染 + 幽灵卡注入。

    不持有 Flet 控件引用——通过参数传入。
    幽灵卡回调通过 set_callbacks() 设置。
    """

    # 回调工厂：fn(prop_type, tid, rec) → (on_accept, on_reject)
    _callback_factory = None

    @classmethod
    def set_callbacks(cls, factory):
        """设置幽灵卡 accept/reject 回调工厂。
        factory(prop_type, tid, rec) → (on_accept_fn, on_reject_fn)
        """
        cls._callback_factory = factory

    # ── 幽灵卡类型判断（消除重复的核心逻辑）──

    @staticmethod
    def get_ghost_info(t) -> GhostInfo:
        """根据任务属性确定幽灵卡类型和渲染位置。"""
        schedule_data = BoardRenderer._extract_schedule_data(t)

        if t.ai_priority:
            return GhostInfo(
                prop_type="classify", render_column="triage",
                source_column="backlog",
                display_priority=t.ai_priority.value,
                task_data={
                    "id": t.id, "title": t.title, "description": t.description,
                    "ata_chapter": t.ata_chapter, "aircraft_reg": t.aircraft_reg,
                    "priority": t.ai_priority.value, "task_type": t.task_type.value,
                    "zone": t.zone,
                    "estimated_hours": t.estimated_hours,
                })

        if schedule_data:
            task_data = {
                "id": t.id, "title": t.title, "description": t.description,
                "ata_chapter": t.ata_chapter, "aircraft_reg": t.aircraft_reg,
                "priority": t.priority.value, "task_type": t.task_type.value,
                "zone": t.zone,
                "estimated_hours": float(schedule_data.get("estimated_hours", t.estimated_hours)),
            }
            for k in ("planned_start", "planned_end", "employee_id", "employee_name"):
                if schedule_data.get(k):
                    task_data[k] = schedule_data[k]
            return GhostInfo(
                prop_type="schedule", render_column="scheduled",
                source_column="triage",
                display_priority=t.priority.value,
                task_data=task_data)

        if getattr(t, 'ai_acceptance_recommendation', None):
            return GhostInfo(
                prop_type="acceptance", render_column=t.status.value,
                source_column=t.status.value,
                display_priority=t.priority.value,
                task_data={
                    "id": t.id, "title": t.title,
                    "recommendation": t.ai_acceptance_recommendation,
                    "reason": getattr(t, 'ai_acceptance_reason', ''),
                    "aircraft_reg": t.aircraft_reg, "ata_chapter": t.ata_chapter,
                    "priority": t.priority.value,
                    "employee_name": t.employee_name,
                })

        return GhostInfo(
            prop_type="new_task", render_column=t.status.value,
            source_column=t.status.value,
            display_priority=t.priority.value,
            task_data={
                "id": t.id, "title": t.title, "description": t.description,
                "ata_chapter": t.ata_chapter, "aircraft_reg": t.aircraft_reg,
                "priority": t.priority.value, "task_type": t.task_type.value,
                "zone": t.zone, "estimated_hours": t.estimated_hours,
            })

    # ── 看板数据填充 ──

    @staticmethod
    def fill_board(kanban_board, fleet_status):
        """首次渲染看板（从 state 加载全部数据）。"""
        if not kanban_board:
            return
        bs = board_service.get_board()
        tasks_map = {}
        ai_proposed = {}
        for ids in bs.tasks.values():
            for tid in ids:
                t = state.get_task(tid)
                if not t:
                    continue
                if t.ai_proposed:
                    ai_proposed[tid] = t
                else:
                    tasks_map[tid] = t
        kanban_board.render_board(bs, tasks_map, do_update=False)
        BoardRenderer.render_ghost_cards(kanban_board, ai_proposed)
        if fleet_status:
            fleet_status.update_summary(
                board_service.get_fleet_summary(), bs.filters)

    # ── 增量刷新 ──

    @staticmethod
    def refresh_incremental(kanban_board, fleet_status):
        """列级增量更新：保留幽灵卡，只换任务卡片。"""
        from app.ui.widgets.ai_ghost_card import AIGhostCard

        bs = board_service.get_board()
        tasks_map = {}
        ai_proposed = {}
        for ids in bs.tasks.values():
            for tid in ids:
                t = state.get_task(tid)
                if not t:
                    continue
                if t.ai_proposed:
                    ai_proposed[tid] = t
                else:
                    tasks_map[tid] = t

        # 首次渲染 → 全量
        if not kanban_board._columns:
            kanban_board.render_board(bs, tasks_map)
            BoardRenderer.render_ghost_cards(kanban_board, ai_proposed)
            if fleet_status:
                fleet_status.update_summary(
                    board_service.get_fleet_summary(), bs.filters)
            return

        # 后续刷新 → 列级原地更新
        existing_ghost_ids = set()
        for col in kanban_board._columns.values():
            if not hasattr(col, 'card_list') or not col.card_list:
                continue
            ghosts_in_col = [c for c in col.card_list.controls
                           if isinstance(c, AIGhostCard)]
            for g in ghosts_in_col:
                existing_ghost_ids.add(g.proposal.id.replace("ai_", ""))

            task_ids = bs.tasks.get(col.column.id, [])
            col_tasks = [tasks_map[tid] for tid in task_ids if tid in tasks_map]
            col.column.task_count = len(col_tasks)
            col._update_count_text()
            new_cards = col._build_cards(col_tasks)
            col.card_list.controls = ghosts_in_col + new_cards

        # 幽灵卡增量同步
        new_ghost_ids = set(ai_proposed.keys())
        for col in kanban_board._columns.values():
            if not hasattr(col, 'card_list') or not col.card_list:
                continue
            stale = [c for c in col.card_list.controls
                     if isinstance(c, AIGhostCard)
                     and c.proposal.id.replace("ai_", "") not in new_ghost_ids]
            for c in stale:
                try:
                    col.card_list.controls.remove(c)
                except ValueError:
                    pass

        for tid in new_ghost_ids - existing_ghost_ids:
            BoardRenderer._add_one(kanban_board, tid, ai_proposed[tid])

        try:
            kanban_board.column_row.update()
        except Exception:
            pass
        if fleet_status:
            fleet_status.update_summary(
                board_service.get_fleet_summary(), bs.filters)

    # ── 幽灵卡注入 ──

    @staticmethod
    def render_ghost_cards(kanban_board, ai_tasks: dict):
        """批量渲染幽灵卡片（首次渲染后调用）。

        回调通过 BoardRenderer.set_callbacks() 预先设置。
        """
        from app.ui.widgets.ai_ghost_card import AIGhostCard

        # 清除旧幽灵
        for col in kanban_board._columns.values():
            if not hasattr(col, 'card_list') or not col.card_list:
                continue
            to_remove = [c for c in col.card_list.controls
                        if isinstance(c, AIGhostCard)]
            for c in to_remove:
                col.card_list.controls.remove(c)

        # 注入新幽灵
        for tid, t in ai_tasks.items():
            BoardRenderer._add_one(kanban_board, tid, t)

        if ai_tasks:
            try:
                kanban_board.column_row.update()
                kanban_board.update()
            except Exception:
                pass

    @staticmethod
    def add_single_ghost(kanban_board, tid: str, t):
        """添加单个幽灵卡片（增量刷新时调用）。

        回调通过 BoardRenderer.set_callbacks() 预先设置。
        """
        BoardRenderer._add_one(kanban_board, tid, t)

    @staticmethod
    def _add_one(kanban_board, tid: str, t):
        """添加单个幽灵卡片到对应列。"""
        from app.ui.widgets.ai_ghost_card import AIGhostCard, AIProposal

        info = BoardRenderer.get_ghost_info(t)

        if info.render_column not in kanban_board._columns:
            return
        col = kanban_board._columns[info.render_column]
        if not hasattr(col, 'card_list') or not col.card_list:
            return

        proposal = AIProposal(
            id=f"ai_{tid}",
            proposal_type=info.prop_type,
            task_data=info.task_data,
            source_column=info.source_column,
            target_column=info.render_column,
        )

        # 通过回调工厂获取 accept/reject 回调
        on_acc = on_rej = None
        if BoardRenderer._callback_factory:
            rec = info.task_data.get("recommendation", "")
            on_acc, on_rej = BoardRenderer._callback_factory(
                info.prop_type, tid, rec)

        ghost = AIGhostCard(proposal, on_accept=on_acc, on_reject=on_rej)
        col.card_list.controls.insert(0, ghost)

    # ── 内部 ──

    @staticmethod
    def _extract_schedule_data(t) -> dict:
        for sug in (t.ai_suggestions or []):
            if isinstance(sug, dict) and sug.get("proposal_type") == "schedule":
                return sug
        return {}
