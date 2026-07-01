"""可复用的全屏变暗遮罩组件.

用法：
    # 简单弹窗
    dimmer = OverlayDimmer.open(page, my_panel)

    # 点击遮罩关闭
    dimmer = OverlayDimmer.open(page, my_panel, on_dimmer_click=lambda: dimmer.close())

    # 自定义变暗程度
    dimmer = OverlayDimmer.open(page, my_panel, dim_opacity=0.6)

原理（Flet 0.28.3）：
    page.overlay 中的控件没有父布局来分配 expand，必须显式设尺寸。
    #00000066 等 hex-alpha 格式在 0.28.3 不渲染，需用 Container.opacity：
    page.overlay.append(Stack([
        Container(width=page.width, height=page.height,
                  bgcolor=ft.Colors.BLACK, opacity=0.4),  ← 变暗层
        panel_content,                                      ← 内容面板
    ], width=page.width, height=page.height))
"""

import flet as ft


class OverlayDimmer:
    """全屏变暗遮罩 + 内容面板。

    构造参数（仅 __init__ 接收，不作为实例属性暴露）：
        dim_opacity: 变暗程度 0.0-1.0（默认 0.4）
        on_dimmer_click: 点击遮罩区域时的回调（常用于关闭）
        close_on_dimmer_click: 点击遮罩是否自动关闭（默认 True）

    公开接口：
        is_open: bool — 是否已打开
        show() / close() — 显示 / 关闭
        OverlayDimmer.open(page, content, **kw) — 工厂方法，创建并立即打开
    """

    def __init__(self, page: ft.Page, content: ft.Control, *,
                 dim_opacity: float = 0.4,
                 on_dimmer_click=None,
                 close_on_dimmer_click: bool = True):
        self._page = page
        self._content = content
        self._dim_opacity = max(0.0, min(1.0, dim_opacity))
        self._on_dimmer_click = on_dimmer_click
        self._close_on_dimmer = close_on_dimmer_click
        self._overlay: ft.Stack | None = None
        self._open = False

    # ── 公开 API ──

    @classmethod
    def open(cls, page: ft.Page, content: ft.Control, **kwargs) -> "OverlayDimmer":
        """工厂方法：创建并立即打开。"""
        inst = cls(page, content, **kwargs)
        inst.show()
        return inst

    def show(self):
        """显示遮罩。重复调用无效果。"""
        if self._open:
            return
        self._open = True
        self._overlay = self._build()
        self._page.overlay.append(self._overlay)
        self._page.update()

    def close(self):
        """关闭遮罩。"""
        if not self._open or not self._page:
            return
        self._open = False
        try:
            self._page.overlay.remove(self._overlay)
        except (ValueError, AssertionError):
            pass
        self._overlay = None
        self._page.update()

    @property
    def is_open(self) -> bool:
        return self._open

    # ── 内部 ──

    def _build(self) -> ft.Stack:
        pw, ph = self._page.width, self._page.height

        def on_dim_click(e):
            if self._on_dimmer_click:
                self._on_dimmer_click()
            elif self._close_on_dimmer:
                self.close()

        # Container.opacity 作用于整层（0.28.3 确认可用）
        dimmer = ft.Container(
            width=pw, height=ph,
            bgcolor=ft.Colors.BLACK,
            opacity=self._dim_opacity,
            on_click=on_dim_click,
        )

        return ft.Stack(
            [dimmer, self._content],
            width=pw, height=ph,
        )
