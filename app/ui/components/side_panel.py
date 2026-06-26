"""右侧详情面板."""
from __future__ import annotations

import flet as ft
from app.config.theme import theme
from app.core.models.task import Task
from app.ui.widgets.badge import ATABadge, PriorityBadge, StatusBadge, TaskTypeBadge


class SidePanel(ft.Container):
    def __init__(self, on_close=None, **_kw):
        super().__init__(
            width=theme.side_panel_width,
            bgcolor=theme.surface,
            border=ft.border.only(left=ft.BorderSide(1, theme.border)),
            visible=False,
            padding=0,
        )
        self._on_close = on_close
        self._task: Task | None = None

    @property
    def is_open(self):
        return self.visible

    def open(self, task: Task):
        self._task = task
        self.visible = True
        self.content = self._build()
        self.update()

    def close(self):
        self.visible = False
        self._task = None
        self.content = None
        self.update()
        if self._on_close:
            self._on_close()

    def toggle(self, task: Task):
        if self.visible and self._task and self._task.id == task.id:
            self.close()
        else:
            self.open(task)

    def _build(self):
        t = self._task
        if not t:
            return ft.Text("无数据")

        ff = theme.font_family
        g = theme.pad_lg  # 左右统一内边距

        # ── 工具栏 ──
        close_btn = ft.IconButton(
            icon=ft.Icons.CLOSE,
            icon_size=theme.font_xl,
            icon_color=theme.text_secondary,
            on_click=lambda e: self.close(),
        )

        toolbar = ft.Container(
            content=ft.Row([
                ft.Text("任务详情", size=theme.font_lg,
                        weight=ft.FontWeight.W_600,
                        color=theme.text_primary, font_family=ff),
                ft.Container(expand=True),
                close_btn,
            ]),
            padding=ft.padding.only(left=g, top=theme.pad_md,
                                    right=theme.pad_md, bottom=theme.pad_sm),
        )

        # ── 标签 ──
        badges = ft.Container(
            content=ft.Row([
                PriorityBadge(t.priority.value),
                StatusBadge(t.status.value),
                TaskTypeBadge(t.task_type.value),
                ATABadge(t.ata_chapter) if t.ata_chapter else ft.Text(""),
            ], spacing=theme.spacing_sm, wrap=True),
            padding=ft.padding.only(left=g, right=g, bottom=theme.pad_sm),
        )

        # ── 字段 ──
        def field(label, value):
            return ft.Container(
                content=ft.Column([
                    ft.Text(label, size=theme.font_xs,
                            color=theme.text_disabled, font_family=ff),
                    ft.Text(value, size=theme.font_sm,
                            color=theme.text_primary, font_family=ff),
                ], spacing=2),
                padding=ft.padding.only(
                    left=g, right=g, top=theme.pad_xs, bottom=theme.pad_xs),
            )

        fields = ft.Column([
            field("标题", t.title),
            field("描述", t.description or "无描述"),
            field("飞机", f"{t.aircraft_reg} · {t.aircraft_model}" if t.aircraft_reg else "未指定"),
            field("ATA 章节", t.ata_chapter or "未分类"),
            field("区域", t.zone or "未指定"),
            field("负责人", t.assignee or "未分配"),
            field("预估工时", f"{t.estimated_hours}h" if t.estimated_hours else "未设置"),
            field("截止日期", t.due_date.strftime("%Y-%m-%d %H:%M") if t.due_date else "未设置"),
        ], spacing=0)

        # ── 合规 ──
        comp = []
        if t.ad_numbers:
            comp.append(field("适航指令 AD", ", ".join(t.ad_numbers)))
        if t.is_rii:
            comp.append(ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.WARNING_AMBER, size=theme.font_md,
                            color=theme.error),
                    ft.Text("必检项目 (RII)", size=theme.font_sm,
                            color=theme.error, weight=ft.FontWeight.W_600,
                            font_family=ff),
                ], spacing=theme.spacing_sm),
                padding=ft.padding.only(
                    left=g, right=g, top=theme.pad_xs, bottom=theme.pad_xs),
            ))

        # ── 检查清单 ──
        ch = []
        for item in t.checklist:
            ch.append(ft.Checkbox(
                label=item.text, value=item.completed,
                label_style=ft.TextStyle(
                    size=theme.font_sm, font_family=ff,
                    color=theme.text_secondary if item.completed
                    else theme.text_primary),
                check_color=theme.success,
            ))
        ch_done = sum(1 for i in t.checklist if i.completed)
        ch_total = len(t.checklist)
        ch_content = ft.Column([
            ft.Row([
                ft.Text("检查清单", size=theme.font_sm,
                        weight=ft.FontWeight.W_600, color=theme.text_primary,
                        font_family=ff),
                ft.Text(f"{ch_done}/{ch_total}", size=theme.font_xs,
                        color=theme.text_disabled, font_family=ff),
            ], spacing=theme.spacing_md),
        ] + (ch if ch else [
            ft.Text("无检查项", size=theme.font_xs, color=theme.text_disabled,
                    font_family=ff),
        ]), spacing=theme.spacing_xs)

        ch_section = ft.Container(
            content=ch_content,
            padding=ft.padding.only(
                left=g, right=g, top=theme.pad_xs, bottom=theme.pad_xs),
        )

        # ── AI ──
        ai_sec = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.PSYCHOLOGY_OUTLINED, size=theme.font_lg,
                            color=theme.type_removal_install),
                    ft.Text("AI 建议", size=theme.font_sm,
                            weight=ft.FontWeight.W_600,
                            color=theme.text_primary, font_family=ff),
                ], spacing=theme.spacing_sm),
                ft.Text(
                    "AI Agent 将在后续版本集成\n"
                    "• 自动 ATA 分类  •  操作步骤建议\n"
                    "• 合规检查提醒  •  相关知识检索",
                    size=theme.font_xs, color=theme.text_disabled,
                    font_family=ff),
            ], spacing=theme.pad_sm),
            padding=ft.padding.all(theme.pad_md),
            margin=ft.margin.only(
                left=g, right=g, top=theme.pad_md, bottom=g),
            border_radius=theme.radius_md,
            border=ft.border.all(1, theme.border),
        )

        # ── 组装 ──
        sep = lambda: ft.Divider(height=1, color=theme.divider)

        body = [
            toolbar, sep(), badges, sep(), fields,
        ]
        if comp:
            body.append(sep())
            body.append(ft.Text("合规信息", size=theme.font_sm,
                                weight=ft.FontWeight.W_600,
                                color=theme.warning, font_family=ff))
            body.extend(comp)
        body.append(sep())
        body.append(ch_section)
        body.append(ai_sec)

        return ft.ListView(
            controls=body,
            spacing=0,
            expand=True,
            padding=0,
        )
