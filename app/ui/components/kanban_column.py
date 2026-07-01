"""看板列组件."""
from __future__ import annotations

import json

import flet as ft
from app.config.theme import theme, s
from app.core.models.kanban import ColumnConfig
from app.core.models.task import Task
from app.ui.components.task_card import TaskCard

# 模块级拖拽上下文：绕过 page.get_control() 的 ID 查找问题
_drag_ctx: dict | None = None


class KanbanColumn(ft.Container):
    def __init__(self, column: ColumnConfig, tasks: list[Task],
                 on_card_click=None, on_card_context_menu=None,
                 on_drop=None, on_column_menu=None):
        self.column = column
        self._on_cc = on_card_click
        self._on_ccm = on_card_context_menu
        self._on_drop = on_drop
        self._on_cm = on_column_menu
        self._collapsed = False

        self.card_list = ft.ListView(
            controls=self._build_cards(tasks),
            spacing=s(8),
            padding=ft.padding.all(s(8)),
            expand=True,
        )

        self._drop_target = ft.DragTarget(
            content=ft.Column([
                ft.Divider(height=1, color=theme.divider),
                ft.Container(content=self.card_list, expand=True),
            ], spacing=0),
            data=self.column.id,
            on_accept=self._on_drag_accept,
            on_will_accept=self._on_drag_will_accept,
            on_leave=self._on_drag_leave,
        )

        self._body = ft.Container(
            content=self._drop_target,
            expand=True,
        )

        super().__init__(
            content=ft.Column([
                self._header(),
                self._body,
            ], spacing=0),
            width=theme.column_width,
            bgcolor=theme.surface,
            border_radius=s(10),
            animate=ft.Animation(200, ft.AnimationCurve.EASE_OUT),
        )

    def _build_cards(self, tasks: list[Task]):
        return [
            ft.Draggable(
                content=TaskCard(t, on_click=self._on_cc, on_context_menu=self._on_ccm),
                data=json.dumps({"tid": t.id, "col": self.column.id}),
                content_feedback=TaskCard(t, ghost=True),
                content_when_dragging=TaskCard(t, ghost=True),
                on_drag_start=self._on_card_drag_start,
                on_drag_complete=self._on_card_drag_complete,
            )
            for t in tasks
        ]

    def _header(self):
        col = self.column
        ff = theme.font_family
        wc, wcol = theme.text_secondary, theme.text_secondary
        txt = ""
        if col.wip_limit:
            txt = f" {col.task_count}/{col.wip_limit}"
            if col.wip_exceeded:
                wcol = theme.error
            elif col.wip_percentage > 0.7:
                wcol = theme.warning

        return ft.Container(
            content=ft.Row([
                ft.Container(width=3, height=s(18),
                             bgcolor=theme.column_header, border_radius=2),
                ft.Text(col.title, size=theme.font_sm,
                        weight=ft.FontWeight.W_600,
                        color=theme.text_primary, font_family=ff),
                ft.Text(txt, size=theme.font_xs, color=wcol,
                        weight=ft.FontWeight.W_600
                        if col.wip_exceeded else ft.FontWeight.W_400,
                        font_family=ff),
                ft.Container(expand=True),
                ft.IconButton(
                    icon=ft.Icons.MORE_HORIZ, icon_size=s(16),
                    icon_color=theme.text_disabled,
                    tooltip=ft.Tooltip(
                        message=f"{col.title} — 排序/折叠",
                        bgcolor=theme.card,
                        text_style=ft.TextStyle(font_family=ff)),
                    on_click=lambda e: self._on_cm
                    and self._on_cm(col.id)),
                ft.IconButton(
                    icon=ft.Icons.EXPAND_LESS if not self._collapsed
                    else ft.Icons.EXPAND_MORE,
                    icon_size=s(16),
                    icon_color=theme.text_disabled,
                    tooltip=ft.Tooltip(
                        message="折叠/展开",
                        bgcolor=theme.card,
                        text_style=ft.TextStyle(font_family=ff)),
                    on_click=self._toggle_collapse),
            ], spacing=s(6)),
            padding=ft.padding.only(left=s(12), top=s(6),
                                    right=s(6), bottom=s(6)),
        )

    def _toggle_collapse(self, e):
        self._collapsed = not self._collapsed
        cols = self.content.controls
        header_row = cols[0].content
        if self._collapsed:
            cols[1].visible = False
            for ctrl in header_row.controls:
                if isinstance(ctrl, ft.IconButton) and ctrl.icon in (
                    ft.Icons.EXPAND_LESS, ft.Icons.EXPAND_MORE
                ):
                    ctrl.icon = ft.Icons.EXPAND_MORE
        else:
            cols[1].visible = True
            for ctrl in header_row.controls:
                if isinstance(ctrl, ft.IconButton) and ctrl.icon in (
                    ft.Icons.EXPAND_LESS, ft.Icons.EXPAND_MORE
                ):
                    ctrl.icon = ft.Icons.EXPAND_LESS
        self.update()

    # ═══════════════════════ 拖放 ═══════════════════════

    def _on_card_drag_start(self, e):
        global _drag_ctx
        ctrl = e.control
        raw = ctrl.data
        try:
            _drag_ctx = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            _drag_ctx = None

    def _on_card_drag_complete(self, e):
        """同列拖放补抓：DragTarget 不向子孙发送事件."""
        global _drag_ctx
        ctx = _drag_ctx
        _drag_ctx = None
        if not ctx or not self.page or not self._on_drop:
            return
        tid = ctx.get("tid")
        src_col = ctx.get("col")
        if not tid or src_col != self.column.id:
            return
        self._on_drop(tid, self.column.id)

    def _on_drag_accept(self, e):
        """跨列移动."""
        global _drag_ctx
        ctx = _drag_ctx
        _drag_ctx = None
        if not ctx or not self._on_drop:
            return
        tid = ctx.get("tid")
        src_col = ctx.get("col")
        if not tid or src_col != self.column.id:
            self._on_drop(tid, self.column.id)

    def _on_drag_will_accept(self, e):
        self.border = ft.border.all(2, theme.info)
        if self.page:
            self.update()

    def _on_drag_leave(self, e):
        self.border = None
        if self.page:
            self.update()

    def update_tasks(self, tasks: list[Task]):
        self.card_list.controls = self._build_cards(tasks)
        self.column.task_count = len(tasks)
        self.update()
