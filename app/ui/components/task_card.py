"""任务卡片组件."""
from __future__ import annotations

import flet as ft
from app.config.theme import theme, s
from app.core.models.task import Task
from app.ui.widgets.badge import ATABadge, PriorityBadge, TaskTypeBadge


class TaskCard(ft.Container):
    def __init__(self, task: Task, on_click=None,
                 on_context_menu=None, ghost: bool = False, **_kw):
        self.task = task
        self._on_click = on_click
        self._on_context_menu = on_context_menu
        self._ghost = ghost
        pc = theme.priority_color(task.priority.value)
        pd = theme.pad_md

        super().__init__(
            content=self._build(pc, pd),
            width=theme.card_width,
            bgcolor=theme.card if not ghost else ft.Colors.TRANSPARENT,
            border_radius=theme.radius_md,
            padding=ft.padding.all(pd),
            animate=ft.Animation(150, ft.AnimationCurve.EASE_OUT),
            shadow=(ft.BoxShadow(spread_radius=0, blur_radius=4,
                     color="#00000030", offset=ft.Offset(0, 1))
                    if not ghost else None),
            on_click=lambda e: self._on_click and self._on_click(task.id),
            on_long_press=lambda e: self._on_context_menu
            and self._on_context_menu(task.id, e),
            on_hover=self._handle_hover,
        )
        if ghost:
            self.border = ft.border.all(1.5, theme.border)
            self.opacity = 0.45

    def _build(self, pc, pd):
        t = self.task
        ff = theme.font_family
        header = ft.Row([
            ft.Container(width=4, height=round(18*1.5), bgcolor=pc, border_radius=2),
            ATABadge(t.ata_chapter, "sm") if t.ata_chapter else ft.Text(""),
            ft.Container(expand=True),
            TaskTypeBadge(t.task_type.value, "sm"),
        ], spacing=theme.spacing_sm)

        title = ft.Text(
            t.title[:38] + "…" if len(t.title) > 40 else t.title,
            size=theme.font_md, weight=ft.FontWeight.W_600,
            color=theme.text_primary, font_family=ff,
            max_lines=2, overflow=ft.TextOverflow.ELLIPSIS)

        ac_info = (f"{t.aircraft_reg} · {t.aircraft_model}"
                   if t.aircraft_reg else "未指定飞机")
        if t.zone: ac_info += f" · Zone {t.zone}"
        aircraft = ft.Text(ac_info, size=theme.font_xs,
                           color=theme.text_secondary, font_family=ff)

        bottom = []
        if t.assignee:
            bottom.append(ft.Row([
                ft.Icon(ft.Icons.PERSON_OUTLINE, size=theme.font_xs,
                        color=theme.text_disabled),
                ft.Text(t.assignee, size=theme.font_xs,
                        color=theme.text_secondary, font_family=ff),
            ], spacing=2))
        if t.estimated_hours > 0:
            bottom.append(ft.Row([
                ft.Icon(ft.Icons.TIMER_OUTLINED, size=theme.font_xs,
                        color=theme.text_disabled),
                ft.Text(f"{t.estimated_hours}h", size=theme.font_xs,
                        color=theme.text_secondary, font_family=ff),
            ], spacing=2))
        if t.due_date:
            dc = theme.error if t.is_overdue else theme.text_secondary
            bottom.append(ft.Row([
                ft.Icon(ft.Icons.CALENDAR_TODAY_OUTLINED,
                        size=theme.font_xs, color=dc),
                ft.Text(t.due_date.strftime("%m-%d %H:%M"),
                        size=theme.font_xs, color=dc, font_family=ff),
            ], spacing=2))

        tags = []
        if t.is_rii:
            tags.append(ft.Container(
                content=ft.Text("RII", size=round(9*1.5), color=theme.error,
                                weight=ft.FontWeight.W_700, font_family=ff),
                padding=ft.padding.only(left=4, top=1, right=4, bottom=1),
                border_radius=2, border=ft.border.all(1, theme.error)))
        if not t.parts_available:
            tags.append(ft.Container(
                content=ft.Text("零件待确认", size=round(9*1.5),
                                color=theme.warning, font_family=ff),
                padding=ft.padding.only(left=4, top=1, right=4, bottom=1),
                border_radius=2, border=ft.border.all(1, theme.warning)))
        if t.is_overdue:
            tags.append(ft.Container(
                content=ft.Text("逾期", size=round(9*1.5), color=theme.error,
                                weight=ft.FontWeight.W_700, font_family=ff),
                padding=ft.padding.only(left=4, top=1, right=4, bottom=1),
                border_radius=2, bgcolor="#FF000015"))

        ctrls = [header, title, aircraft]
        if bottom:
            ctrls.append(ft.Row(bottom, spacing=theme.pad_md))
        if tags:
            ctrls.append(ft.Row(tags, spacing=theme.spacing_sm))

        done, total = t.checklist_progress()
        if total > 0:
            ctrls.append(ft.ProgressBar(
                value=done / total, width=theme.card_width - pd * 2,
                height=3, color=theme.success, bgcolor=theme.border))

        return ft.Column(ctrls, spacing=theme.spacing_sm)

    def _handle_hover(self, e):
        if self._ghost:
            return
        if e.data == "true":
            self.border = ft.border.all(1, theme.info)
            self.bgcolor = theme.card_hover
            self.shadow = ft.BoxShadow(spread_radius=1, blur_radius=8,
                                       color="#00000050", offset=ft.Offset(0, 2))
            self.scale = 1.01
        else:
            self.border = None
            self.bgcolor = theme.card
            self.shadow = ft.BoxShadow(spread_radius=0, blur_radius=4,
                                       color="#00000030", offset=ft.Offset(0, 1))
            self.scale = 1.0
        try:
            self.update()
        except AssertionError:
            pass  # 拖拽中看板刷新后旧卡片已移出页面
