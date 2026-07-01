"""幽灵文本输入 — AI 建议的内联显示."""
from __future__ import annotations

from typing import Callable

import flet as ft

from app.config.theme import theme


class GhostTextField(ft.Column):
    """支持 AI 幽灵文本建议的文本输入控件。

    行为：
    - 用户输入 → 停止 typing → 触发 AI 推理
    - AI 返回 → 以半透明文本显示在输入后方
    - Tab → 接受建议
    - Esc → 拒绝建议
    - 继续输入 → 自动清除
    """

    def __init__(
        self,
        value: str = "",
        label: str = "",
        hint_text: str = "",
        multiline: bool = False,
        min_lines: int = 1,
        max_lines: int = 5,
        width: int | None = None,
        on_change: Callable | None = None,
        on_accept_ghost: Callable | None = None,
        on_request_suggestion: Callable | None = None,
    ):
        super().__init__(spacing=0)

        self._value = value
        self._ghost_text = ""
        self._on_change = on_change
        self._on_accept_ghost = on_accept_ghost
        self._on_request_suggestion = on_request_suggestion

        # 底层输入框
        self.text_field = ft.TextField(
            value=value,
            label=label,
            hint_text=hint_text,
            multiline=multiline,
            min_lines=min_lines,
            max_lines=max_lines,
            width=width,
            border_color=theme.border,
            focused_border_color=theme.info,
            text_style=ft.TextStyle(
                color=theme.text_primary,
                size=14,
                font_family="monospace",
            ),
            bgcolor=theme.card,
            on_change=self._handle_change,
            on_blur=self._handle_blur,
            on_focus=self._handle_focus,
        )

        # 幽灵文本覆盖层（在 text_field 上方）
        self.ghost_display = ft.Text(
            "",
            size=14,
            color=self._alpha(theme.text_secondary, 0.4),
            font_family="monospace",
            visible=False,
        )

        self.controls = [self.text_field]

    @property
    def value(self) -> str:
        return self.text_field.value or ""

    @value.setter
    def value(self, v: str):
        self._value = v
        self.text_field.value = v

    @property
    def ghost_text(self) -> str:
        return self._ghost_text

    @ghost_text.setter
    def ghost_text(self, text: str):
        self._ghost_text = text
        self._update_ghost_display()

    def _handle_change(self, e):
        """用户输入变化时：清除幽灵文本，触发 AI 请求。"""
        self._value = e.control.value
        self._ghost_text = ""

        if self._on_change:
            self._on_change(self._value)

        # 如果有 AI 请求回调，触发（实际使用中会做防抖）
        if self._on_request_suggestion and self._value:
            self._on_request_suggestion(self._value)

        self._update_ghost_display()

    def _handle_blur(self, e):
        """失去焦点时隐藏幽灵文本。"""
        pass

    def _handle_focus(self, e):
        """获得焦点时显示幽灵文本。"""
        self._update_ghost_display()

    def _update_ghost_display(self):
        """更新幽灵文本覆盖显示。"""
        if self._ghost_text and self._value:
            display = f"{self._value}{self._ghost_text}"
            self.ghost_display.value = display
            self.ghost_display.visible = True
        else:
            self.ghost_display.visible = False

    def on_keyboard(self, e: ft.KeyboardEvent):
        """处理快捷键：
        Tab → 接受幽灵文本
        Esc → 清除幽灵文本
        """
        if e.key == "Tab" and self._ghost_text:
            new_value = self._value + self._ghost_text
            self.text_field.value = new_value
            self._value = new_value
            self._ghost_text = ""
            if self._on_accept_ghost:
                self._on_accept_ghost(new_value)
            self._update_ghost_display()
            e.handled = True
        elif e.key == "Escape" and self._ghost_text:
            self._ghost_text = ""
            self._update_ghost_display()
            e.handled = True

    @staticmethod
    def _alpha(hex_color: str, alpha: float) -> str:
        hex_color = hex_color.lstrip("#")
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        return f"#{int(255 * alpha):02x}{r:02x}{g:02x}{b:02x}"
