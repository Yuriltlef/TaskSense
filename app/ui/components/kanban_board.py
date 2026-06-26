"""看板主体组件."""
from __future__ import annotations

import flet as ft

from app.config.theme import theme
from app.core.models.kanban import BoardState
from app.core.models.task import Task
from app.ui.components.kanban_column import KanbanColumn


class KanbanBoard(ft.Container):
    def __init__(self, on_card_click, on_card_context_menu,
                 on_drop, on_column_menu=None):
        super().__init__(expand=True, padding=8, bgcolor=theme.bg)
        self._on_card_click = on_card_click
        self._on_card_context_menu = on_card_context_menu
        self._on_drop = on_drop
        self._on_column_menu = on_column_menu
        self._columns: dict[str, KanbanColumn] = {}

        self.column_row = ft.Row(
            controls=[],
            spacing=theme.column_gap,
            scroll=ft.ScrollMode.AUTO,
            vertical_alignment=ft.CrossAxisAlignment.START,
            expand=True,
        )
        self.content = self.column_row

    def render_board(self, board_state: BoardState, tasks_map: dict[str, Task],
                     do_update: bool = True):
        column_controls = []
        self._columns = {}
        for col in board_state.columns:
            task_ids = board_state.tasks.get(col.id, [])
            col_tasks = [tasks_map[tid] for tid in task_ids if tid in tasks_map]
            col.task_count = len(col_tasks)
            column_controls.append(KanbanColumn(
                column=col, tasks=col_tasks,
                on_card_click=self._on_card_click,
                on_card_context_menu=self._on_card_context_menu,
                on_drop=self._on_drop,
                on_column_menu=self._on_column_menu,
            ))
        self.column_row.controls = column_controls
        if do_update:
            self.update()

    def update_column(self, col_id: str, tasks: list[Task]):
        if col_id in self._columns:
            self._columns[col_id].update_tasks(tasks)
            self.update()
