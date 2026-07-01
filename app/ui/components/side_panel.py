"""任务详情面板."""
from __future__ import annotations

import flet as ft
from app.config.theme import theme, s
from app.core.models.task import Task
from app.ui.widgets.badge import ATABadge, PriorityBadge, StatusBadge, TaskTypeBadge


class SidePanel(ft.Container):
    def __init__(self, on_close=None, on_edit=None, **_kw):
        super().__init__(
            width=theme.side_panel_width, bgcolor=theme.surface,
            border=ft.border.only(left=ft.BorderSide(1, theme.border)),
            visible=False, padding=0,
        )
        self._on_close = on_close
        self._on_edit = on_edit
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
        ff = theme.font_family; g = s(14)

        close_btn = ft.IconButton(icon=ft.Icons.CLOSE, icon_size=s(15),
                                  icon_color=theme.text_secondary,
                                  on_click=lambda e: self.close())
        edit_btn = ft.IconButton(icon=ft.Icons.EDIT_OUTLINED, icon_size=s(15),
                                 icon_color=theme.text_secondary,
                                 tooltip=ft.Tooltip(message="编辑任务",
                                                    bgcolor=theme.card),
                                 on_click=lambda e: self._on_edit
                                 and self._on_edit(t))

        header = ft.Container(
            content=ft.Row([
                ft.Text("任务详情", size=s(13), weight=ft.FontWeight.W_600,
                        color=theme.text_primary, font_family=ff),
                ft.Container(expand=True), edit_btn, close_btn,
            ]),
            padding=ft.padding.only(left=g, top=s(5), right=s(4), bottom=s(5)),
            border=ft.border.only(bottom=ft.BorderSide(1, theme.border)))

        badges = ft.Container(
            content=ft.Row([
                PriorityBadge(t.priority.value), StatusBadge(t.status.value),
                TaskTypeBadge(t.task_type.value),
                ATABadge(t.ata_chapter) if t.ata_chapter else ft.Text(""),
            ], spacing=6, wrap=True),
            padding=ft.padding.only(left=g, right=g, top=s(8), bottom=s(4)))

        def row(l, v):
            return ft.Container(
                content=ft.Column([
                    ft.Text(l, size=s(11), color=theme.text_disabled, font_family=ff),
                    ft.Text(v, size=s(12), color=theme.text_primary, font_family=ff),
                ], spacing=2),
                padding=ft.padding.only(left=g, right=g, top=s(4), bottom=s(4)))

        def section(title):
            return ft.Container(
                content=ft.Text(title, size=s(11), weight=ft.FontWeight.W_600,
                                color=theme.text_secondary, font_family=ff),
                padding=ft.padding.only(left=g, right=g, top=s(10), bottom=s(2)))

        items = [header, badges, ft.Divider(height=1, color=theme.divider)]

        # 基本信息
        items.append(section("基本信息"))
        items.append(row("标题", t.title))
        items.append(row("飞机", f"{t.aircraft_reg} · {t.aircraft_model}"
                         if t.aircraft_reg else "未指定"))
        items.append(row("ATA 章节", t.ata_chapter or "未分类"))
        items.append(row("区域", t.zone or "未指定"))

        # 人员与时间
        items.append(section("人员与时间"))
        items.append(row("负责人", t.assignee or "未分配"))
        if t.created_by:
            items.append(row("创建者", t.created_by))
        if t.inspector:
            items.append(row("检查员 (RII)", t.inspector))
        items.append(row("预估工时", f"{t.estimated_hours}h"
                         if t.estimated_hours else "未设置"))
        if t.actual_hours:
            items.append(row("实际工时", f"{t.actual_hours}h"))
        if t.due_date:
            dc = theme.error if t.is_overdue else theme.text_primary
            items.append(ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.CALENDAR_TODAY_OUTLINED, size=s(12), color=dc),
                    ft.Text(t.due_date.strftime("%Y-%m-%d %H:%M"),
                            size=s(12), color=dc, font_family=ff),
                ], spacing=6),
                padding=ft.padding.only(left=g, right=g, top=s(4), bottom=s(4))))

        # 描述
        if t.description:
            items.append(section("描述"))
            items.append(ft.Container(
                content=ft.Text(t.description, size=s(12),
                                color=theme.text_secondary, font_family=ff),
                padding=ft.padding.only(left=g, right=g, top=s(2), bottom=s(8))))

        # 清单进度
        done, total = t.checklist_progress()
        if total > 0:
            items.append(section(f"检查清单 ({done}/{total})"))
            items.append(ft.Container(
                content=ft.ProgressBar(value=done / total,
                                       color=theme.success, bgcolor=theme.border,
                                       height=4),
                padding=ft.padding.only(left=g, right=g, top=s(2), bottom=s(8))))

        # 标签/标记
        tags = []
        if t.is_rii:
            tags.append(ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.WARNING_AMBER, size=s(14), color=theme.error),
                    ft.Text("必检项目 (RII)", size=s(11), color=theme.error,
                            weight=ft.FontWeight.W_600, font_family=ff),
                ], spacing=4),
                padding=ft.padding.only(left=s(8), top=s(3), right=s(8), bottom=s(3)),
                border_radius=s(4), border=ft.border.all(1, theme.error),
                bgcolor="#FF000010"))
        if not t.parts_available:
            tags.append(ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.INVENTORY_2_OUTLINED, size=s(14), color=theme.warning),
                    ft.Text("零件待确认", size=s(11), color=theme.warning, font_family=ff),
                ], spacing=4),
                padding=ft.padding.only(left=s(8), top=s(3), right=s(8), bottom=s(3)),
                border_radius=s(4), border=ft.border.all(1, theme.warning)))
        if tags:
            items.append(ft.Container(
                content=ft.Column(tags, spacing=s(6)),
                padding=ft.padding.only(left=g, right=g, top=s(8), bottom=s(8))))

        return ft.ListView(items, spacing=0, expand=True, padding=0)
