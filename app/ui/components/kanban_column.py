"""看板列组件."""
from __future__ import annotations

import flet as ft
from app.config.theme import theme
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
        self._on_cm = on_column_menu

        self.card_list = ft.ListView(
            controls=[TaskCard(t, on_click=on_card_click,
                               on_context_menu=on_card_context_menu)
                      for t in tasks],
            spacing=theme.pad_sm,
            padding=ft.padding.all(theme.pad_sm),
            expand=True,
        )

        super().__init__(
            content=ft.Column([
                self._header(),
                ft.Divider(height=1, color=theme.divider),
                self.card_list,
            ], spacing=0),
            width=theme.column_width,
            bgcolor=theme.surface,
            border_radius=theme.radius_lg,
        )

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
                ft.Container(width=3, height=round(16*1.5),
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
                    icon=ft.Icons.MORE_HORIZ, icon_size=theme.font_lg,
                    icon_color=theme.text_disabled,
                    tooltip=ft.Tooltip(
                        message=f"{col.title} — 排序/折叠",
                        bgcolor=theme.card,
                        text_style=ft.TextStyle(font_family=theme.font_family)),
                    on_click=lambda e: self._on_cm
                    and self._on_cm(col.id)),
            ], spacing=theme.spacing_sm),
            padding=ft.padding.only(left=theme.pad_md, top=theme.pad_sm,
                                    right=theme.pad_md, bottom=theme.pad_sm),
        )

    def update_tasks(self, tasks: list[Task]):
        self.card_list.controls = [
            TaskCard(t, on_click=self._on_cc, on_context_menu=self._on_ccm)
            for t in tasks]
        self.column.task_count = len(tasks)
        self.update()
