"""Agent 输入框组件 — 单行 Row，整容器聚焦描边。

用法:
    inp = ChatInput(on_send=callback, on_stop=callback)
    # 获取输入文本: inp.value
    # 清空: inp.clear()
    # 切换忙碌状态: inp.set_busy(True) → 发送按钮变为中止按钮
"""
from __future__ import annotations

import flet as ft
from app.config.theme import theme


class ChatInput(ft.Container):
    """输入区：整容器圆角底 + 透明 TextField + 圆形发送/中止按钮。

    聚焦时整容器边框从 idle → accent 色描边。
    """

    def __init__(
        self,
        on_send=None,
        on_stop=None,
        hint: str = "输入消息... Enter 发送",
        width: float | None = None,
    ):
        super().__init__(border_radius=theme.radius_md + 2)
        self._on_send = on_send
        self._on_stop = on_stop
        self._busy = False

        self._input = ft.TextField(
            hint_text=hint,
            border=ft.InputBorder.NONE,
            border_color=ft.Colors.TRANSPARENT,
            focused_border_color=ft.Colors.TRANSPARENT,
            filled=False,
            cursor_color=theme.text_primary,
            text_style=ft.TextStyle(color=theme.text_primary, size=theme.font_md,
                                    font_family=theme.font_family),
            hint_style=ft.TextStyle(color=theme.text_disabled, size=theme.font_md,
                                    font_family=theme.font_family),
            border_radius=0,
            min_lines=1, max_lines=6, multiline=True, shift_enter=True,
            content_padding=ft.padding.only(left=4, top=10, right=4, bottom=10),
            on_submit=self._on_submit,
            on_focus=lambda e: self._set_border(True),
            on_blur=lambda e: self._set_border(False),
        )

        self._send_btn = ft.IconButton(
            ft.Icons.ARROW_UPWARD, icon_size=18, icon_color="#ffffff",
            on_click=self._on_btn_click, splash_radius=18,
            style=ft.ButtonStyle(
                shape=ft.CircleBorder(),
                bgcolor=theme.info,
                padding=ft.padding.all(8),
            ),
        )

        self.content = ft.Row(
            [
                ft.Container(self._input, expand=True),
                self._send_btn,
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        self.bgcolor = "#1a1a1a"
        self.border = ft.border.all(1, "#2a2a2a")
        self.padding = ft.padding.only(left=14, top=4, right=6, bottom=4)

    @property
    def value(self) -> str:
        return self._input.value or ""

    @value.setter
    def value(self, v: str):
        self._input.value = v
        self._input.update()

    def clear(self):
        self._input.value = ""
        self._input.update()

    def focus(self):
        self._input.focus()

    def set_busy(self, busy: bool):
        """切换忙碌状态：busy=True → 按钮变为红色中止图标。"""
        self._busy = busy
        if busy:
            self._send_btn.icon = ft.Icons.STOP
            self._send_btn.icon_color = "#ffffff"
            self._send_btn.style = ft.ButtonStyle(
                shape=ft.CircleBorder(),
                bgcolor=theme.error,
                padding=ft.padding.all(8),
            )
        else:
            self._send_btn.icon = ft.Icons.ARROW_UPWARD
            self._send_btn.icon_color = "#ffffff"
            self._send_btn.style = ft.ButtonStyle(
                shape=ft.CircleBorder(),
                bgcolor=theme.info,
                padding=ft.padding.all(8),
            )
        self._send_btn.update()
        # busy 时禁用输入
        self._input.read_only = busy
        self._input.update()

    def _on_submit(self, e):
        if self._busy:
            return
        txt = self.value.strip()
        if not txt or not self._on_send:
            return
        self._on_send(txt)

    def _on_btn_click(self, e):
        if self._busy and self._on_stop:
            self._on_stop()
        else:
            txt = self.value.strip()
            if txt and self._on_send:
                self._on_send(txt)

    def _set_border(self, focused: bool):
        self.border = ft.border.all(1, theme.info if focused else "#2a2a2a")
        self.update()
