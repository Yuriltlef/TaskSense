"""AI 建议 & 机队状态栏."""
from __future__ import annotations

import flet as ft
from app.config.theme import theme


class FleetStatusBar(ft.Container):
    def __init__(self, summary=None):
        super().__init__(
            padding=ft.padding.only(left=theme.pad_lg, top=theme.pad_sm,
                                    right=theme.pad_lg, bottom=theme.pad_sm),
            bgcolor=theme.surface,
            border=ft.border.only(bottom=ft.BorderSide(1, theme.border)),
        )
        self._build(summary or {})

    def _build(self, s):
        ff = theme.font_family
        self.content = ft.Row([
            self._stat("机队", s.get("total", 0), theme.text_primary),
            self._stat("运行中", s.get("operational", 0), theme.success),
            self._stat("维修中", s.get("in_maintenance", 0), theme.warning),
            self._stat("AOG", s.get("aog", 0), theme.error),
            ft.VerticalDivider(width=1, color=theme.border),
            self._stat("逾期任务", s.get("total_overdue", 0), theme.error),
            self._stat("未关闭故障", s.get("total_open_defects", 0), theme.warning),
        ], spacing=round(20*1.5))

    def _stat(self, label, value, color):
        tips = {
            "机队": "机队飞机总数",
            "运行中": "当前适航、正常运行的飞机",
            "维修中": "正在执行维护的飞机",
            "AOG": "Aircraft on Ground — 停飞待修",
            "逾期任务": "已超过截止日期的任务数",
            "未关闭故障": "尚未修复的故障报告数",
        }
        return ft.Container(
            content=ft.Row([
                ft.Text(str(value), size=theme.font_xl, weight=ft.FontWeight.W_700,
                        color=color, font_family=theme.font_family),
                ft.Text(label, size=theme.font_xs, color=theme.text_disabled,
                        font_family=theme.font_family),
            ], spacing=theme.spacing_sm),
            tooltip=ft.Tooltip(
                message=tips.get(label, label),
                bgcolor=theme.card,
                text_style=ft.TextStyle(font_family=theme.font_family)),
        )

    def update_summary(self, summary):
        self._build(summary); self.update()


class AISuggestionPanel(ft.Container):
    def __init__(self, **_kw):
        super().__init__(
            padding=ft.padding.all(theme.pad_md),
            border_radius=theme.radius_md,
            border=ft.border.all(1, theme.border),
        )
        ff = theme.font_family
        self.content = ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.PSYCHOLOGY_OUTLINED, size=theme.font_lg,
                        color=theme.type_removal_install),
                ft.Text("AI 建议", size=theme.font_sm, weight=ft.FontWeight.W_600,
                        color=theme.text_primary, font_family=ff),
            ], spacing=theme.spacing_sm),
            ft.Text("AI Agent 功能将在后续版本集成\n• 自动 ATA 分类\n• 操作步骤建议\n• 合规检查提醒\n• 相关知识检索",
                    size=theme.font_xs, color=theme.text_disabled, font_family=ff),
        ], spacing=theme.pad_sm)
