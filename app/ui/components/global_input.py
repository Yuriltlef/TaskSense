"""全局输入栏 — VS Code 风格命令/搜索/Agent 交互."""
from __future__ import annotations

import flet as ft
from app.config.theme import theme


class GlobalInputBar(ft.Container):
    """VS Code 风格全局输入栏。

    功能：
    - 搜索任务（输入即搜索）
    - Agent 自然语言交互（> 前缀）
    - 快捷命令（/ 前缀）
    """

    def __init__(self, on_search=None, on_agent_query=None, on_command=None):
        super().__init__(
            padding=ft.padding.only(left=theme.pad_lg, top=theme.pad_xs,
                                    right=theme.pad_lg, bottom=theme.pad_xs),
            bgcolor=theme.surface,
            border=ft.border.only(bottom=ft.BorderSide(1, theme.border)),
        )
        self._on_search = on_search
        self._on_agent_query = on_agent_query
        self._on_command = on_command
        self._results: list[dict] = []

        ff = theme.font_family

        # 输入框
        self._input = ft.TextField(
            hint_text="搜索任务 / > 询问 AI / / 命令...",
            border_color=ft.Colors.TRANSPARENT,
            focused_border_color=ft.Colors.TRANSPARENT,
            text_style=ft.TextStyle(color=theme.text_primary,
                                    size=theme.font_sm, font_family=ff),
            hint_style=ft.TextStyle(color=theme.text_disabled,
                                    size=theme.font_sm, font_family=ff),
            prefix_icon=ft.Icon(ft.Icons.SEARCH, color=theme.text_disabled,
                                size=theme.font_lg),
            bgcolor=theme.card,
            border_radius=theme.radius_md,
            content_padding=ft.padding.only(
                left=theme.pad_sm, top=theme.pad_xs,
                right=theme.pad_sm, bottom=theme.pad_xs),
            dense=True,
            on_change=self._on_input_change,
            on_submit=self._on_submit,
            on_focus=self._on_focus,
            on_blur=self._on_blur,
        )

        # 下拉建议面板
        self._suggestions = ft.Column(spacing=0, visible=False)

        self.content = ft.Column([
            self._input,
            self._suggestions,
        ], spacing=0)

        # 内置命令
        self._commands = [
            {"label": "搜索任务", "prefix": "", "icon": ft.Icons.SEARCH,
             "hint": "输入关键词搜索任务"},
            {"label": "询问 AI", "prefix": ">", "icon": ft.Icons.PSYCHOLOGY_OUTLINED,
             "hint": "> 起落架排故步骤是什么？"},
            {"label": "生成报告", "prefix": "/report", "icon": ft.Icons.DESCRIPTION,
             "hint": "生成每日维护报告"},
            {"label": "合规检查", "prefix": "/compliance", "icon": ft.Icons.VERIFIED_USER,
             "hint": "检查当前 AD/SB 合规状态"},
            {"label": "知识库搜索", "prefix": "/kb", "icon": ft.Icons.BOOK,
             "hint": "/kb ATA 32 landing gear"},
            {"label": "新建任务", "prefix": "/new", "icon": ft.Icons.ADD_TASK,
             "hint": "/new 起落架排故"},
        ]

    @property
    def value(self) -> str:
        return self._input.value or ""

    def _on_input_change(self, e):
        val = (e.control.value or "").strip()

        # 空输入：显示命令提示
        if not val:
            self._show_command_hints()
            self._suggestions.visible = True
            self.content.update()
            return

        # > 前缀：AI 模式
        if val.startswith(">"):
            self._show_ai_hint(val)
            self._suggestions.visible = True
            self.content.update()
            return

        # / 前缀：命令模式
        if val.startswith("/"):
            self._filter_commands(val)
            self._suggestions.visible = True
            self.content.update()
            return

        # 搜索模式
        self._suggestions.visible = False
        self.content.update()
        if self._on_search and len(val) >= 1:
            self._on_search(val)

    def _on_submit(self, e):
        val = (self._input.value or "").strip()
        if not val:
            return

        if val.startswith(">") and self._on_agent_query:
            self._on_agent_query(val[1:].strip())
        elif val.startswith("/"):
            parts = val.split(maxsplit=1)
            cmd = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else ""
            if self._on_command:
                self._on_command(cmd, arg)
        elif self._on_search:
            self._on_search(val)

        self._input.value = ""
        self._suggestions.visible = False
        self.content.update()

    def _on_focus(self, e):
        if not self._input.value:
            self._show_command_hints()
            self._suggestions.visible = True
            self.content.update()

    def _on_blur(self, e):
        self._suggestions.visible = False
        self.content.update()

    def _show_command_hints(self):
        ff = theme.font_family
        items = []
        for cmd in self._commands:
            items.append(
                ft.Container(
                    content=ft.Row([
                        ft.Icon(cmd["icon"], size=theme.font_md,
                                color=theme.text_secondary),
                        ft.Text(cmd["label"], size=theme.font_sm,
                                color=theme.text_primary, font_family=ff),
                        ft.Container(expand=True),
                        ft.Text(cmd["hint"], size=theme.font_xs,
                                color=theme.text_disabled, font_family=ff),
                    ], spacing=theme.spacing_md),
                    padding=ft.padding.only(left=theme.pad_md, top=theme.pad_xs,
                                            right=theme.pad_md, bottom=theme.pad_xs),
                    on_click=lambda e, p=cmd["prefix"]: self._select_prefix(p),
                )
            )
        self._suggestions.controls = items

    def _show_ai_hint(self, val):
        ff = theme.font_family
        q = val[1:].strip()
        self._suggestions.controls = [
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.PSYCHOLOGY_OUTLINED, size=theme.font_md,
                            color=theme.type_removal_install),
                    ft.Text(f"询问 AI: {q or '...'}", size=theme.font_sm,
                            color=theme.text_primary, font_family=ff),
                    ft.Container(expand=True),
                    ft.Text("Enter 发送", size=theme.font_xs,
                            color=theme.text_disabled, font_family=ff),
                ], spacing=theme.spacing_md),
                padding=ft.padding.only(left=theme.pad_md, top=theme.pad_xs,
                                        right=theme.pad_md, bottom=theme.pad_xs),
            )
        ]

    def _filter_commands(self, val):
        ff = theme.font_family
        prefix = val.lower()
        filtered = [c for c in self._commands
                    if c["prefix"].lower().startswith(prefix)
                    or prefix in c["label"].lower()]
        self._suggestions.controls = [
            ft.Container(
                content=ft.Row([
                    ft.Icon(c["icon"], size=theme.font_md, color=theme.text_secondary),
                    ft.Text(c["label"], size=theme.font_sm,
                            color=theme.text_primary, font_family=ff),
                    ft.Container(expand=True),
                    ft.Text(c["prefix"], size=theme.font_xs,
                            color=theme.text_disabled, font_family=ff),
                ], spacing=theme.spacing_md),
                padding=ft.padding.only(left=theme.pad_md, top=theme.pad_xs,
                                        right=theme.pad_md, bottom=theme.pad_xs),
                on_click=lambda e, p=c["prefix"]: self._select_prefix(p),
            )
            for c in filtered
        ]

    def _select_prefix(self, prefix: str):
        self._input.value = prefix + (" " if prefix and not prefix.endswith(" ") else "")
        self._input.focus()
        self._on_input_change(ft.ControlEvent(
            target=self._input, name="change", data="",
            control=self._input, page=None))
