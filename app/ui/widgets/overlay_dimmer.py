"""可复用的全屏变暗遮罩组件.

用法：
    OverlayDimmer.init_slot(board_page)            # 在 build() 中注册原生槽位
    dlg = OverlayDimmer.open(page, my_panel)       # 弹窗自动使用原生槽位（响应式）

原理：
    优先使用页面内容树中的 Stack 槽位（Flet 原生 expand 布局→实时响应缩放），
    回退到 page.overlay（手动尺寸→仅 RESIZED 时更新）。
"""

import flet as ft


class OverlayDimmer:
    """全屏变暗遮罩 + 内容面板。"""

    _slot: ft.Container | None = None      # 页面内容树中的遮罩槽位
    _active: "OverlayDimmer | None" = None  # 当前打开的实例

    def __init__(self, page: ft.Page, content: ft.Control, *,
                 dim_opacity: float = 0.4,
                 on_dimmer_click=None,
                 close_on_dimmer_click: bool = True):
        self._page = page
        self._content = content
        self._dim_opacity = max(0.0, min(1.0, dim_opacity))
        self._on_dimmer_click = on_dimmer_click
        self._close_on_dimmer = close_on_dimmer_click
        self._use_slot = OverlayDimmer._slot is not None
        self._old_on_resized = None
        self._open = False

    # ── 公开 API ──

    @classmethod
    def init_slot(cls, board_page):
        """注册页面内容树中的原生遮罩槽位（在 build() 中调用）。"""
        cls._slot = getattr(board_page, '_dimmer_slot', None)

    @classmethod
    def open(cls, page, content, **kwargs) -> "OverlayDimmer":
        inst = cls(page, content, **kwargs)
        inst.show()
        return inst

    def show(self):
        if self._open:
            return
        self._open = True

        if self._use_slot:
            # 原生槽位：Flet 自动布局→实时响应缩放
            OverlayDimmer._active = self
            OverlayDimmer._slot.content = self._build_inline()
            OverlayDimmer._slot.visible = True
            try: OverlayDimmer._slot.update()
            except Exception: pass
            self._old_on_resized = self._page.on_resized
            self._page.on_resized = lambda e: self._on_resized(e)
        else:
            # 回退到 overlay（旧方案）
            self._overlay = self._build_overlay()
            self._page.overlay.append(self._overlay)
            self._page.update()
            self._old_on_resized = self._page.on_resized
            self._page.on_resized = lambda e: self._on_resized(e)

    def close(self):
        if not self._open:
            return
        self._open = False

        if self._old_on_resized:
            self._page.on_resized = self._old_on_resized

        if self._use_slot:
            OverlayDimmer._active = None
            OverlayDimmer._slot.visible = False
            OverlayDimmer._slot.content = None
            try: OverlayDimmer._slot.update()
            except Exception: pass
        else:
            try:
                self._page.overlay.remove(self._overlay)
            except (ValueError, AssertionError):
                pass
            self._page.update()

    @property
    def is_open(self) -> bool:
        return self._open

    # ── 内部 ──

    def _on_resized(self, e):
        """窗口缩放回调（仅 overlay 回退模式需要手动更新）。"""
        if self._use_slot or not self._open:
            return
        if hasattr(self, '_overlay') and self._overlay:
            pw, ph = self._page.width, self._page.height
            self._overlay.width = pw
            self._overlay.height = ph
            try: self._overlay.update()
            except Exception: pass

    def _build_inline(self) -> ft.Stack:
        """原生槽位模式：expand自动填满 + alignment.center自动居中。"""
        # 清除内容面板的手动定位（让 alignment.center 自动居中）
        if hasattr(self._content, 'left'):
            self._content.left = None
        if hasattr(self._content, 'top'):
            self._content.top = None
        dimmer = ft.Container(
            expand=True,
            bgcolor=ft.Colors.BLACK,
            opacity=self._dim_opacity,
            on_click=self._on_dim_click,
        )
        return ft.Stack(
            [dimmer, self._content],
            expand=True,
            alignment=ft.alignment.center,
        )

    def _build_overlay(self) -> ft.Stack:
        """Overlay 回退模式：手动设置尺寸。"""
        pw, ph = self._page.width or 1280, self._page.height or 900
        dimmer = ft.Container(
            width=pw, height=ph,
            bgcolor=ft.Colors.BLACK,
            opacity=self._dim_opacity,
            on_click=self._on_dim_click,
        )
        return ft.Stack(
            [dimmer, self._content],
            width=pw, height=ph,
        )

    def _on_dim_click(self, e):
        if self._on_dimmer_click:
            self._on_dimmer_click()
        elif self._close_on_dimmer:
            self.close()
