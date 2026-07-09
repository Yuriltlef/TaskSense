"""命令面板 — Ctrl+K 打开，Esc 关闭."""
from __future__ import annotations

import flet as ft
from app.config.theme import theme, s


class CommandBar:
    """命令面板 — overlay Stack，支持搜索过滤 + 键盘导航。"""

    def __init__(self, on_execute=None):
        self._on_execute = on_execute
        self._page: ft.Page | None = None
        self._overlay: ft.Container | None = None
        self._search: ft.TextField | None = None
        self._results: ft.Column | None = None

        self._commands = [
            # 导航
            {"l": "打开 AI 助手面板", "i": ft.Icons.PSYCHOLOGY_OUTLINED, "a": "open_ai", "g": "面板"},
            {"l": "打开筛选面板", "i": ft.Icons.FILTER_ALT_OUTLINED, "a": "open_filter", "g": "面板"},
            {"l": "打开员工工作台", "i": ft.Icons.PERSON_OUTLINE, "a": "open_employee", "g": "面板"},
            # AI 命令
            {"l": "AI 生成任务大纲", "i": ft.Icons.ARTICLE_OUTLINED, "a": "/outline", "g": "AI 工具"},
            {"l": "AI 生成任务", "i": ft.Icons.PLAYLIST_ADD_OUTLINED, "a": "/gen", "g": "AI 工具"},
            {"l": "AI 分类任务", "i": ft.Icons.LABEL_OUTLINED, "a": "/classify", "g": "AI 工具"},
            {"l": "AI 排程任务", "i": ft.Icons.CALENDAR_MONTH_OUTLINED, "a": "/schedule", "g": "AI 工具"},
            {"l": "AI 验收任务", "i": ft.Icons.VERIFIED_OUTLINED, "a": "/acceptance", "g": "AI 工具"},
            {"l": "AI 生成报告", "i": ft.Icons.ASSESSMENT_OUTLINED, "a": "/report", "g": "AI 工具"},
            {"l": "AI 任务审核", "i": ft.Icons.FACT_CHECK_OUTLINED, "a": "/review", "g": "AI 工具"},
            # 看板
            {"l": "看板摘要 (/summary)", "i": ft.Icons.DASHBOARD_OUTLINED, "a": "/summary", "g": "命令"},
            {"l": "切换严格模式", "i": ft.Icons.SHIELD_OUTLINED, "a": "toggle_strict", "g": "命令"},
        ]

    def show(self, page: ft.Page):
        if self._overlay:
            return
        self._page = page

        ff = theme.font_family
        self._search = ft.TextField(
            hint_text="搜索命令... (/ 命令、面板、AI 工具)",
            border_color=ft.Colors.TRANSPARENT,
            focused_border_color=ft.Colors.TRANSPARENT,
            text_style=ft.TextStyle(color=theme.text_primary, size=s(14), font_family=ff),
            hint_style=ft.TextStyle(color=theme.text_disabled, size=s(13), font_family=ff),
            prefix_icon=ft.Icon(ft.Icons.SEARCH, color=theme.text_disabled, size=s(16)),
            autofocus=True,
            on_change=self._on_search,
            on_submit=self._on_submit,
        )

        self._results = ft.Column(spacing=0)
        self._build_results("")

        panel = ft.Container(
            content=ft.Column([
                ft.Container(
                    content=ft.Row([
                        ft.Text("⌘", size=s(14), color=theme.text_disabled, font_family=ff),
                        self._search,
                    ], spacing=0),
                    padding=ft.padding.only(left=s(16), top=s(10), right=s(16), bottom=s(10)),
                    border=ft.border.only(bottom=ft.BorderSide(1, theme.border)),
                ),
                ft.Container(
                    content=ft.ListView([self._results], spacing=0, expand=True, padding=0),
                    height=320,
                    padding=ft.padding.symmetric(vertical=s(6)),
                ),
                ft.Container(
                    content=ft.Row([
                        ft.Text("↑↓ 导航  Enter 选择  Esc 关闭", size=s(9),
                                color=theme.text_disabled, font_family=ff),
                        ft.Container(expand=True),
                        ft.Text(f"{len(self._commands)} 条命令", size=s(9),
                                color=theme.text_disabled, font_family=ff),
                    ], spacing=s(8)),
                    padding=ft.padding.only(left=s(16), top=s(6), right=s(16), bottom=s(8)),
                    border=ft.border.only(top=ft.BorderSide(1, theme.border)),
                ),
            ], spacing=0, tight=True),
            bgcolor=theme.surface,
            border_radius=s(10),
            border=ft.border.all(1, theme.border),
            shadow=ft.BoxShadow(spread_radius=1, blur_radius=20, color=theme.dialog_shadow),
            width=560,
            top=max(80, (page.height - 420) // 2),
            left=(page.width - 560) // 2,
        )

        dimmer = ft.Container(
            ft.GestureDetector(
                content=ft.Container(expand=True),
                on_tap=lambda _: self.close(),
            ),
            width=page.width, height=page.height,
        )

        self._overlay = ft.Stack([dimmer, panel], width=page.width, height=page.height)
        page.overlay.append(self._overlay)
        page.update()

    def close(self):
        if self._overlay and self._page:
            try:
                self._page.overlay.remove(self._overlay)
            except (ValueError, AssertionError):
                pass
            self._page.update()
        self._overlay = None
        self._page = None

    def _build_results(self, query: str):
        q = query.lower()
        items = [c for c in self._commands if q in c["l"].lower() or q in c["g"].lower()]
        groups: dict[str, list] = {}
        for item in items:
            groups.setdefault(item["g"], []).append(item)

        ff = theme.font_family
        ctrls = []
        for gn, group_items in groups.items():
            ctrls.append(ft.Container(
                content=ft.Text(gn, size=s(10), weight=ft.FontWeight.W_600,
                                color=theme.text_disabled, font_family=ff),
                padding=ft.padding.only(left=s(16), top=s(6), bottom=s(2)),
            ))
            for item in group_items:
                ctrls.append(self._btn(item))
        self._results.controls = ctrls

    def _btn(self, item):
        ff = theme.font_family
        return ft.Container(
            content=ft.Row([
                ft.Icon(item["i"], size=s(14), color=theme.text_secondary),
                ft.Text(item["l"], size=s(12), color=theme.text_primary, font_family=ff),
            ], spacing=s(8)),
            padding=ft.padding.symmetric(horizontal=s(16), vertical=s(7)),
            border_radius=0,
            ink=True,
            on_click=lambda e, a=item["a"]: self._select(a),
        )

    def _on_search(self, e):
        self._build_results(e.control.value or "")

    def _on_submit(self, e):
        q = (self._search.value or "").strip()
        if not q:
            return
        # 优先匹配精确命令
        matches = [c for c in self._commands if q.lower() in c["l"].lower()]
        if matches:
            self._select(matches[0]["a"])
        else:
            self._select(q)

    def _select(self, action: str):
        self.close()
        if self._on_execute:
            self._on_execute(action, action)
