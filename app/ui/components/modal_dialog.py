"""通用模态弹窗 — OverlayDimmer 变暗遮罩 + 居中面板.

用法:
    dlg = ModalDialog(page, content=..., width=460)
    dlg.open()
    dlg.close()
"""

import flet as ft
from app.config.theme import theme, s
from app.ui.widgets.overlay_dimmer import OverlayDimmer


class ModalDialog:
    """居中半透明遮罩 + 面板弹窗。

    面板默认 bg=theme.surface (#0e0e0e)，和主界面列背景一致。
    """

    def __init__(self, page: ft.Page, content: ft.Control,
                 width: int = 460, height: int = 360,
                 bgcolor: str | None = None, on_close=None,
                 close_on_dimmer_click: bool = True):
        self._page = page
        self._on_close = on_close
        self._close_on_dimmer = close_on_dimmer_click
        self._dimmer: OverlayDimmer | None = None
        self._w, self._h = width, height

        panel_bg = bgcolor or theme.surface
        self._panel = ft.Container(
            content=content,
            width=width, bgcolor=panel_bg,
            border_radius=s(10),
            border=ft.border.all(1, theme.border),
            shadow=ft.BoxShadow(
                spread_radius=1, blur_radius=16, color=theme.dialog_shadow),
        )

    def open(self):
        self._dimmer = OverlayDimmer.open(
            self._page, self._panel, dim_opacity=0.55,
            on_dimmer_click=(lambda: self.close()) if self._close_on_dimmer else None)

    def close(self):
        if self._dimmer:
            self._dimmer.close()
            self._dimmer = None
        if self._on_close:
            self._on_close()
