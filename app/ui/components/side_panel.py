"""任务详情面板."""
from __future__ import annotations

import flet as ft
from app.config.theme import theme
from app.core.models.task import Task
from app.ui.widgets.badge import ATABadge, PriorityBadge, StatusBadge, TaskTypeBadge


class SidePanel(ft.Container):
    def __init__(self, on_close=None, **_kw):
        super().__init__(
            width=theme.side_panel_width, bgcolor=theme.surface,
            border=ft.border.only(left=ft.BorderSide(1, theme.border)),
            visible=False, padding=0,
        )
        self._on_close = on_close
        self._task: Task | None = None

    @property
    def is_open(self): return self.visible

    def open_task(self, task: Task):
        self._task = task; self.visible = True
        self.content = self._build(); self.update()

    def close(self):
        self.visible = False; self._task = None; self.update()
        if self._on_close: self._on_close()

    def toggle_task(self, task: Task):
        if self.visible and self._task and self._task.id == task.id: self.close()
        else: self.open_task(task)

    def _build(self):
        t = self._task
        if not t: return ft.Text("无数据", color=theme.text_disabled)
        ff = theme.font_family; g = theme.pad_lg

        close_btn = ft.IconButton(icon=ft.Icons.CLOSE, icon_size=18,
                                  icon_color=theme.text_secondary,
                                  on_click=lambda e: self.close())

        header = ft.Container(
            content=ft.Row([
                ft.Text("任务详情", size=theme.font_lg, weight=ft.FontWeight.W_600,
                        color=theme.text_primary, font_family=ff),
                ft.Container(expand=True), close_btn,
            ]),
            padding=ft.padding.only(left=g, top=10, right=8, bottom=8),
            border=ft.border.only(bottom=ft.BorderSide(1, theme.border)))

        badges = ft.Container(
            content=ft.Row([
                PriorityBadge(t.priority.value), StatusBadge(t.status.value),
                TaskTypeBadge(t.task_type.value),
                ATABadge(t.ata_chapter) if t.ata_chapter else ft.Text(""),
            ], spacing=6, wrap=True),
            padding=ft.padding.only(left=g, right=g, top=10, bottom=6))

        def row(l, v):
            return ft.Container(
                content=ft.Column([
                    ft.Text(l, size=theme.font_xs, color=theme.text_disabled, font_family=ff),
                    ft.Text(v, size=theme.font_sm, color=theme.text_primary, font_family=ff),
                ], spacing=2),
                padding=ft.padding.only(left=g, right=g, top=5, bottom=5))

        items = [
            header, badges, ft.Divider(height=1, color=theme.divider),
            row("标题", t.title),
            row("飞机", f"{t.aircraft_reg} · {t.aircraft_model}" if t.aircraft_reg else "未指定"),
            row("ATA 章节", t.ata_chapter or "未分类"),
            row("区域", t.zone or "未指定"),
            row("负责人", t.assignee or "未分配"),
            row("预估工时", f"{t.estimated_hours}h" if t.estimated_hours else "未设置"),
            row("截止日期", t.due_date.strftime("%Y-%m-%d %H:%M") if t.due_date else "未设置"),
        ]
        if t.is_rii:
            items.append(ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.WARNING_AMBER, size=16, color=theme.error),
                    ft.Text("必检项目 (RII)", size=theme.font_sm, color=theme.error,
                            weight=ft.FontWeight.W_600, font_family=ff),
                ], spacing=6),
                padding=ft.padding.only(left=g, top=5, bottom=5)))

        return ft.ListView(items, spacing=0, expand=True, padding=0)
