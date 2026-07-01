"""看板列组件."""
from __future__ import annotations

import flet as ft
from app.config.theme import theme, s
from app.core.models.kanban import ColumnConfig
from app.core.models.task import Task
from app.ui.components.task_card import TaskCard


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

        # 卡片列表区域
        self.card_list = ft.ListView(
            controls=self._build_cards(tasks),
            spacing=s(8),
            padding=ft.padding.all(s(8)),
            expand=True,
        )

        # 可折叠的内容区
        self._body = ft.Column([
            ft.Divider(height=1, color=theme.divider),
            self.card_list,
        ], spacing=0)

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
        """构建卡片列表。"""
        return [TaskCard(t, on_click=self._on_cc, on_context_menu=self._on_ccm)
                for t in tasks]

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
        """切换列的折叠/展开状态。"""
        self._collapsed = not self._collapsed
        if self._collapsed:
            self._body.visible = False
            # 找到折叠按钮并更新图标
            header_row = self.content.controls[0].content
            for ctrl in header_row.controls:
                if isinstance(ctrl, ft.IconButton) and ctrl.icon in (
                    ft.Icons.EXPAND_LESS, ft.Icons.EXPAND_MORE
                ):
                    ctrl.icon = ft.Icons.EXPAND_MORE
        else:
            self._body.visible = True
            header_row = self.content.controls[0].content
            for ctrl in header_row.controls:
                if isinstance(ctrl, ft.IconButton) and ctrl.icon in (
                    ft.Icons.EXPAND_LESS, ft.Icons.EXPAND_MORE
                ):
                    ctrl.icon = ft.Icons.EXPAND_LESS
        self.update()

    def update_tasks(self, tasks: list[Task]):
        self.card_list.controls = self._build_cards(tasks)
        self.column.task_count = len(tasks)
        self.update()
