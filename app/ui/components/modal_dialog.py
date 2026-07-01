"""通用模态弹窗 — page.overlay 方式（替代不可用的 page.dialog）.

用法:
    dlg = ModalDialog(page, content=..., width=460)
    dlg.open()
    dlg.close()
"""

import flet as ft
from app.config.theme import theme


class ModalDialog:
    """居中半透明遮罩 + 面板弹窗。"""

    def __init__(self, page: ft.Page, content: ft.Control,
                 width: int = 460, on_close=None):
        self._page = page
        self._on_close = on_close
        self._overlay: ft.Stack | None = None

        # 居中
        cx = (page.width - width) // 2
        cy = max(40, (page.height - 360) // 2)

        panel = ft.Container(
            content=content,
            width=width, bgcolor=theme.surface,
            border_radius=theme.radius_md,
            border=ft.border.all(1, theme.border),
            shadow=ft.BoxShadow(spread_radius=1, blur_radius=16, color="#000000aa"),
            left=cx, top=cy,
        )

        self._overlay = ft.Stack([
            ft.Container(width=page.width, height=page.height,
                         bgcolor="#00000066",
                         on_click=lambda e: self.close()),
            panel,
        ], width=page.width, height=page.height)

    def open(self):
        self._page.overlay.append(self._overlay)
        self._page.update()

    def close(self):
        self._page.overlay.remove(self._overlay)
        self._page.update()
        if self._on_close:
            self._on_close()
