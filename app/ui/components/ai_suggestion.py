"""AI 建议 & 机队状态栏（含筛选指示）."""
from __future__ import annotations

import flet as ft
from app.config.theme import theme, s

# 清除筛选回调（由 BoardPage 注入）
_on_clear_filters = None


def set_filter_clear_callback(cb):
    global _on_clear_filters
    _on_clear_filters = cb


class FleetStatusBar(ft.Container):
    def __init__(self, summary=None, filters=None):
        super().__init__(
            padding=ft.padding.only(left=theme.pad_lg, top=theme.pad_sm,
                                    right=theme.pad_lg, bottom=theme.pad_sm),
            bgcolor=theme.surface,
            border=ft.border.only(bottom=ft.BorderSide(1, theme.border)),
        )
        self._build(summary or {}, filters)

    def _build(self, summary, filters=None):
        ff = theme.font_family
        left_stats = ft.Row([
            self._stat("机队", summary.get("total", 0), theme.text_primary),
            self._stat("运行中", summary.get("operational", 0), theme.success),
            self._stat("维修中", summary.get("in_maintenance", 0), theme.warning),
            self._stat("AOG", summary.get("aog", 0), theme.error),
            ft.VerticalDivider(width=1, color=theme.border),
            self._stat("逾期任务", summary.get("total_overdue", 0), theme.error),
            self._stat("未关闭故障", summary.get("total_open_defects", 0), theme.warning),
        ], spacing=round(20 * 1.5))

        # ── 右侧筛选指示 ──
        right_chips = []
        if filters and filters.is_active:
            for item in filters.summary:
                right_chips.append(ft.Container(
                    content=ft.Text(item, size=s(10), color=theme.info, font_family=ff),
                    bgcolor="#1976d215",
                    border=ft.border.all(1, "#1976d240"),
                    border_radius=s(4),
                    padding=ft.padding.symmetric(horizontal=s(6), vertical=s(2)),
                ))
            right_chips.append(
                ft.TextButton(
                    "清除",
                    icon=ft.Icons.CLOSE,
                    style=ft.ButtonStyle(
                        bgcolor=ft.Colors.TRANSPARENT,
                        color=theme.error,
                        overlay_color="#c6282815",
                        shape=ft.RoundedRectangleBorder(radius=s(4)),
                        padding=ft.padding.symmetric(horizontal=s(6), vertical=s(2)),
                        text_style=ft.TextStyle(size=s(10), font_family=ff),
                    ),
                    on_click=lambda e: _on_clear_filters and _on_clear_filters(),
                ))

        filter_row = ft.Row([
            ft.Icon(ft.Icons.FILTER_ALT_OUTLINED, size=s(12), color=theme.info),
            ft.Text(f"筛选 ({filters.active_filter_count})" if filters else "",
                    size=s(10), color=theme.info, font_family=ff,
                    weight=ft.FontWeight.W_600),
            *right_chips,
        ], spacing=s(5), vertical_alignment=ft.CrossAxisAlignment.CENTER) if right_chips else None

        self.content = ft.Row([
            left_stats,
            ft.Container(expand=True),
            filter_row or ft.Container(),
        ], spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER)

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

    def update_summary(self, summary, filters=None):
        self._build(summary, filters)
        try:
            self.update()
        except AssertionError:
            pass  # 尚未挂载到页面，页面初始化后会自然渲染


