"""命令面板 — Ctrl+K."""
from __future__ import annotations

import flet as ft
from app.config.theme import theme


class CommandBar(ft.AlertDialog):
    def __init__(self, on_execute=None):
        super().__init__(
            modal=True,
            bgcolor=theme.surface,
            shape=ft.RoundedRectangleBorder(radius=theme.radius_lg),
            inset_padding=ft.padding.only(
                left=round(100*1.5), top=round(80*1.5),
                right=round(100*1.5), bottom=round(80*1.5)),
            content_padding=0, title_padding=0,
        )
        self._on_execute = on_execute
        self._defaults = [
            {"l": "创建排故任务", "i": ft.Icons.ADD_TASK, "a": "create_task", "g": "操作"},
            {"l": "创建检查任务", "i": ft.Icons.SEARCH, "a": "create_inspection", "g": "操作"},
            {"l": "生成今日报告", "i": ft.Icons.DESCRIPTION, "a": "generate_report", "g": "操作"},
            {"l": "检查 AD 合规", "i": ft.Icons.VERIFIED_USER, "a": "check_compliance", "g": "操作"},
            {"l": "机队状态总览", "i": ft.Icons.FLIGHT, "a": "goto_fleet", "g": "导航"},
            {"l": "ATA 32 — 起落架", "i": ft.Icons.CATEGORY, "a": "filter_ata_32", "g": "导航"},
            {"l": "ATA 72 — 发动机", "i": ft.Icons.CATEGORY, "a": "filter_ata_72", "g": "导航"},
        ]
        ff = theme.font_family

        self.search = ft.TextField(
            hint_text="搜索任务、跳转、或输入操作...",
            border_color=ft.Colors.TRANSPARENT,
            focused_border_color=ft.Colors.TRANSPARENT,
            text_style=ft.TextStyle(color=theme.text_primary, size=theme.font_lg, font_family=ff),
            hint_style=ft.TextStyle(color=theme.text_disabled, size=theme.font_md, font_family=ff),
            prefix_icon=ft.Icon(ft.Icons.SEARCH, color=theme.text_disabled, size=theme.font_xl),
            autofocus=True,
            on_change=self._on_search,
            on_submit=self._on_submit,
        )

        self.results = ft.Column(spacing=0)
        self._refresh()

        self.content = ft.Column([
            ft.Container(
                content=ft.Row([
                    ft.Text("⌘", size=theme.font_lg, color=theme.text_disabled),
                    self.search,
                ], spacing=0),
                padding=ft.padding.only(left=theme.pad_lg, top=theme.pad_md,
                                        right=theme.pad_lg, bottom=theme.pad_md),
                border=ft.border.only(bottom=ft.BorderSide(1, theme.border)),
            ),
            ft.Container(content=self.results,
                         padding=ft.padding.only(top=theme.pad_sm, bottom=theme.pad_sm)),
        ], spacing=0, width=round(560*1.5))

    def _refresh(self):
        groups = {}
        for item in self._defaults:
            groups.setdefault(item["g"], []).append(item)
        ctrls = []
        ff = theme.font_family
        for gn, items in groups.items():
            ctrls.append(ft.Container(
                content=ft.Text(gn, size=theme.font_xs, weight=ft.FontWeight.W_600,
                                color=theme.text_disabled, font_family=ff),
                padding=ft.padding.only(left=theme.pad_lg, top=theme.pad_sm,
                                        bottom=theme.pad_xs),
            ))
            for item in items:
                ctrls.append(self._btn(item))
        self.results.controls = ctrls

    def _btn(self, item):
        ff = theme.font_family
        return ft.TextButton(
            content=ft.Row([
                ft.Icon(item["i"], size=theme.font_lg, color=theme.text_secondary),
                ft.Text(item["l"], size=theme.font_sm, color=theme.text_primary, font_family=ff),
            ], spacing=theme.spacing_md),
            style=ft.ButtonStyle(
                bgcolor={"hovered": theme.card_hover},
                padding=ft.padding.only(left=theme.pad_lg, top=theme.pad_sm,
                                        right=theme.pad_lg, bottom=theme.pad_sm),
            ),
            on_click=lambda e, a=item["a"]: self._select(a, item["l"]),
        )

    def _on_search(self, e):
        q = (e.control.value or "").lower()
        if not q: self._refresh(); return
        filt = [i for i in self._defaults
                if q in i["l"].lower() or q in i["g"].lower()]
        self.results.controls = [self._btn(i) for i in filt]

    def _on_submit(self, e):
        if self.search.value:
            self._select("nl_query", self.search.value)

    def _select(self, action, value):
        self.open = False
        if self._on_execute: self._on_execute(action, value)

    def show(self, page: ft.Page):
        self.search.value = ""
        self._refresh()
        page.dialog = self
        self.open = True
        page.update()
