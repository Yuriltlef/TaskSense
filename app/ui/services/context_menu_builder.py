# -*- coding: utf-8 -*-
"""右键菜单构建器 — 按列生成的 9 列右键菜单。

从 board_page.py 提取，消除 14 个菜单构建方法对 BoardPage 的耦合。
"""

import flet as ft
from app.config.theme import theme


class ContextMenuBuilder:
    """为 9 个看板列生成右键菜单项列表。

    用法：
        builder = ContextMenuBuilder()
        items = builder.build(column_id, task)
        ContextMenu(items, on_select=callback).show(page, x, y)
    """

    def __init__(self):
        pass

    def build(self, column_id: str, t) -> list[dict]:
        """根据任务所在列生成菜单项列表。"""
        builder = {
            "backlog": self._backlog,
            "triage": self._triage,
            "scheduled": self._scheduled,
            "ready": self._ready,
            "in_progress": self._in_progress,
            "inspection": self._inspection,
            "parts_hold": self._parts_hold,
            "completed": self._completed,
            "archived": self._archived,
        }.get(column_id)
        if not builder:
            return []
        return builder(t)

    # ── 共享菜单项 ──

    @staticmethod
    def _edit_or_view(t) -> dict:
        """已锁定列显示"查看详情"，可编辑列显示"编辑"。"""
        if t.status.value in ("inspection", "completed", "archived"):
            return {"label": "查看详情", "icon": ft.Icons.VISIBILITY_OUTLINED, "action": "edit"}
        return {"label": "编辑", "icon": ft.Icons.EDIT_OUTLINED, "action": "edit"}

    @staticmethod
    def _ai_items() -> list:
        return [
            {"divider": True},
            {"label": "AI 解释任务", "icon": ft.Icons.PSYCHOLOGY_OUTLINED, "action": "ai_explain"},
            {"label": "AI 查找相关文档", "icon": ft.Icons.SEARCH, "action": "search"},
        ]

    @staticmethod
    def _delete_item() -> list:
        return [
            {"divider": True},
            {"label": "删除", "icon": ft.Icons.DELETE_OUTLINE,
             "color": theme.error, "action": "delete",
             "confirm": "确定删除此任务？此操作不可撤销。"},
        ]

    # ── 各列菜单 ──

    def _backlog(self, t) -> list:
        return [
            self._edit_or_view(t),
            {"label": "设置优先级并分类", "icon": ft.Icons.FLAG_OUTLINED,
             "action": "set_priority"},
            {"label": "AI 分类此任务", "icon": ft.Icons.AUTO_AWESOME_OUTLINED,
             "action": "ai_classify", "color": theme.info},
            {"label": "直接归档", "icon": ft.Icons.ARCHIVE_OUTLINED,
             "action": "archive_now", "confirm": "确定跳过所有流程直接归档？"},
            *self._ai_items(),
            *self._delete_item(),
        ]

    def _triage(self, t) -> list:
        return [
            self._edit_or_view(t),
            {"label": "更改优先级", "icon": ft.Icons.FLAG_OUTLINED,
             "action": "change_priority"},
            {"label": "排程", "icon": ft.Icons.CALENDAR_MONTH_OUTLINED,
             "action": "schedule"},
            {"label": "AI 排程此任务", "icon": ft.Icons.AUTO_AWESOME_OUTLINED,
             "action": "ai_schedule", "color": theme.info},
            {"label": "退回待处理", "icon": ft.Icons.UNDO_OUTLINED,
             "action": "move_to:backlog"},
            *self._ai_items(),
            *self._delete_item(),
        ]

    def _scheduled(self, t) -> list:
        return [
            self._edit_or_view(t),
            {"label": "标记就绪", "icon": ft.Icons.CHECK_CIRCLE_OUTLINE,
             "action": "move_to:ready", "color": theme.success},
            {"label": "退回已分类", "icon": ft.Icons.ARROW_BACK_OUTLINED,
             "action": "move_to:triage"},
            {"label": "退回待处理", "icon": ft.Icons.UNDO_OUTLINED,
             "action": "move_to:backlog"},
            *self._ai_items(),
            *self._delete_item(),
        ]

    def _ready(self, t) -> list:
        return [
            self._edit_or_view(t),
            {"label": "开始执行", "icon": ft.Icons.PLAY_ARROW_OUTLINED,
             "action": "move_to:in_progress", "color": theme.success},
            {"label": "重新排程", "icon": ft.Icons.CALENDAR_MONTH_OUTLINED,
             "action": "reschedule"},
            {"label": "阻塞...", "icon": ft.Icons.BLOCK_OUTLINED,
             "action": "block", "color": theme.warning},
            *self._ai_items(),
        ]

    def _in_progress(self, t) -> list:
        return [
            self._edit_or_view(t),
            {"label": "提交验收...", "icon": ft.Icons.ASSIGNMENT_TURNED_IN_OUTLINED,
             "action": "submit", "color": theme.info},
            {"label": "直接完成", "icon": ft.Icons.CHECK_CIRCLE_OUTLINE,
             "action": "complete_direct", "color": theme.success,
             "confirm": "跳过验收直接完成？建议先提交验收审核。"},
            {"label": "阻塞...", "icon": ft.Icons.BLOCK_OUTLINED,
             "action": "block", "color": theme.warning},
            *self._ai_items(),
        ]

    def _inspection(self, t) -> list:
        return [
            self._edit_or_view(t),
            {"label": "验收通过", "icon": ft.Icons.VERIFIED_OUTLINED,
             "action": "approve", "color": theme.success,
             "confirm": "确认验收通过？任务将移至已完成。"},
            {"label": "退回返工", "icon": ft.Icons.REPLAY_OUTLINED,
             "action": "move_to:in_progress", "color": theme.warning},
            {"label": "退回待处理", "icon": ft.Icons.UNDO_OUTLINED,
             "action": "move_to:backlog"},
            {"divider": True},
            {"label": "AI 验收此任务", "icon": ft.Icons.FACT_CHECK_OUTLINED,
             "action": "ai_review_single", "color": theme.info},
            {"label": "AI 解释任务", "icon": ft.Icons.PSYCHOLOGY_OUTLINED,
             "action": "ai_explain"},
            {"label": "AI 查找相关文档", "icon": ft.Icons.SEARCH,
             "action": "search"},
        ]

    def _parts_hold(self, t) -> list:
        return [
            self._edit_or_view(t),
            {"label": "取消阻塞", "icon": ft.Icons.LOCK_OPEN_OUTLINED,
             "action": "unblock", "color": theme.success},
            {"label": "退回已排程", "icon": ft.Icons.ARROW_BACK_OUTLINED,
             "action": "move_to:scheduled"},
            *self._ai_items(),
        ]

    def _completed(self, t) -> list:
        return [
            self._edit_or_view(t),
            {"label": "归档", "icon": ft.Icons.ARCHIVE_OUTLINED,
             "action": "move_to:archived"},
            *self._ai_items(),
        ]

    def _archived(self, t) -> list:
        return [
            self._edit_or_view(t),
            *self._ai_items(),
        ]
