# -*- coding: utf-8 -*-
"""AI 建议 chip 条 — 可复用的建议展示组件。

显示在输入字段下方，每个建议是一个可点击的 chip。
支持双源标注（关键词 / Agent）。
"""

import flet as ft
from app.config.theme import theme, s


def build_suggestion_chip(
    label: str,
    detail: str = "",
    source: str = "keyword",
    on_click=None,
) -> ft.Container:
    """创建单个 AI 建议 chip。

    Args:
        label: chip 显示文本，如 "ATA 32-41-03"
        detail: 悬停详情，如 "Nose Wheel Steering"
        source: 来源 "keyword" | "agent"
        on_click: 点击回调
    """
    ff = theme.font_family

    # 关键词用紫色，Agent 用青色区分
    icon_map = {
        "keyword": (ft.Icons.BOLT_OUTLINED, theme.type_removal_install),
        "agent": (ft.Icons.PSYCHOLOGY_OUTLINED, theme.info),
    }
    icon, color = icon_map.get(source, (ft.Icons.AUTO_AWESOME_OUTLINED, theme.text_secondary))

    return ft.Container(
        content=ft.Row([
            ft.Icon(icon, size=s(9), color=color),
            ft.Text(label, size=s(10), color=theme.text_primary, font_family=ff),
            ft.Text(detail, size=s(9), color=theme.text_disabled, font_family=ff),
        ], spacing=s(4)),
        padding=ft.padding.symmetric(horizontal=s(8), vertical=s(3)),
        border_radius=s(12),
        border=ft.border.all(1, ft.Colors.with_opacity(0.25, color)),
        bgcolor=ft.Colors.with_opacity(0.06, color),
        on_click=on_click,
        ink=True,
    )


class AISuggestionBar(ft.Row):
    """AI 建议 chip 条。

    用法:
        bar = AISuggestionBar()
        bar.show_suggestions([
            {"field": "ata_chapter", "value": "32-41-03",
             "label": "ATA 32-41-03", "detail": "Nose Wheel Steering",
             "source": "keyword"},
        ], on_chip_click=callback)
    """

    def __init__(self):
        super().__init__([], spacing=s(6), wrap=True, tight=True, visible=False)
        self._on_chip_click = None

    def show_suggestions(self, suggestions: list[dict], on_chip_click=None):
        """显示建议 chip 列表。

        Args:
            suggestions: [{field, value, label, detail, source}, ...]
            on_chip_click: 点击 chip 的回调 (field, value)
        """
        self._on_chip_click = on_chip_click
        chips = []
        for s in suggestions:
            chips.append(build_suggestion_chip(
                label=s.get("label", s.get("value", "")),
                detail=s.get("detail", ""),
                source=s.get("source", "keyword"),
                on_click=lambda e, f=s["field"], v=s["value"]: self._handle_click(f, v),
            ))
        self.controls = chips
        self.visible = len(chips) > 0
        try:
            self.update()
        except Exception:
            pass

    def clear(self):
        """清空所有建议。"""
        self.controls = []
        self.visible = False
        try:
            self.update()
        except Exception:
            pass

    def _handle_click(self, field: str, value: str):
        """点击 chip → 执行回调。"""
        if self._on_chip_click:
            self._on_chip_click(field, value)
        self.clear()
