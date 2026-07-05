"""右键菜单 — overlay 定位 + 方形圆角 + 边框 + 动画."""
from __future__ import annotations

import flet as ft
from app.config.theme import theme

_current_menu: "ContextMenu | None" = None


def close_current_menu():
    global _current_menu
    if _current_menu:
        _current_menu._close()
        _current_menu = None
        # 菜单关闭 → 清除卡片蓝色选中高亮
        from app.ui.services.card_highlighter import CardHighlighter
        CardHighlighter.deselect()


def is_menu_open() -> bool:
    return _current_menu is not None


def _hover_item(e, ctrl, item_color):
    """菜单项悬停：背景高亮 + 边框。"""
    if e.data == "true":
        ctrl.bgcolor = theme.card_hover
        ctrl.border = ft.border.all(1, ft.Colors.with_opacity(0.15, item_color))
    else:
        ctrl.bgcolor = None
        ctrl.border = ft.border.all(1, ft.Colors.TRANSPARENT)
    try:
        ctrl.update()
    except Exception:
        pass


# 全局追踪所有已创建的菜单容器，用于防御性清理
_menu_containers: set[int] = set()

class ContextMenu:
    """右键菜单，通过 page.overlay 在鼠标位置弹出。"""

    MENU_W = round(200 * 1.5)

    def __init__(self, items: list[dict], on_select=None):
        self._on_select = on_select
        self._page = None
        self._overlay = None   # _container 即 overlay 实体

        ff = theme.font_family
        menu_ctrls = []
        for item in items:
            if item.get("divider"):
                menu_ctrls.append(ft.Divider(height=1, color=theme.border))
                continue
            c = item.get("color", theme.text_primary)
            confirm_msg = item.get("confirm", None)

            item_ctrl = ft.Container(
                content=ft.Row([
                    ft.Icon(item.get("icon", ft.Icons.CHEVRON_RIGHT),
                            size=18, color=c),
                    ft.Text(item["label"], size=13, color=c, font_family=ff),
                ], spacing=8),
                padding=ft.padding.symmetric(horizontal=12, vertical=8),
                border_radius=6,
                margin=ft.margin.symmetric(horizontal=4),
                border=ft.border.all(1, ft.Colors.TRANSPARENT),
                ink=True,
                on_click=lambda e, a=item["action"], cf=confirm_msg: (
                    self._confirm_then_pick(a, cf) if cf else self._pick(a)),
            )
            item_ctrl.on_hover = (
                lambda e, ctrl=item_ctrl, clr=c: _hover_item(e, ctrl, clr))
            menu_ctrls.append(item_ctrl)

        self._menu_col = ft.Column(menu_ctrls, spacing=1, width=self.MENU_W)
        self._container = ft.Container(
            content=self._menu_col,
            bgcolor=theme.surface,
            border_radius=8,
            border=ft.border.all(1, ft.Colors.with_opacity(0.08, ft.Colors.WHITE)),
            padding=ft.padding.symmetric(vertical=4),
            shadow=ft.BoxShadow(spread_radius=1, blur_radius=16,
                                color="#00000080", offset=ft.Offset(0, 6)),
            animate_opacity=ft.Animation(120, ft.AnimationCurve.EASE_OUT),
            opacity=0,
        )
        self._cid = id(self._container)  # 唯一标识，用于追踪和清理
        _menu_containers.add(self._cid)

    def _close(self):
        _menu_containers.discard(self._cid)
        if self._page and self._overlay:
            self._overlay.visible = False  # 即时视觉隐藏
            try:
                self._page.overlay.remove(self._overlay)
            except (ValueError, AssertionError):
                pass
            self._page.update()
        self._page = None
        self._overlay = None

    def _pick(self, action):
        self._close()
        global _current_menu
        _current_menu = None
        if self._on_select:
            self._on_select(action)

    def _confirm_then_pick(self, action, message):
        page = self._page
        self._close()
        global _current_menu
        _current_menu = None
        if not page:
            return

        from app.ui.components.modal_dialog import ModalDialog
        from app.config.theme import s
        ff = theme.font_family

        def _do_confirm(_):
            dlg.close()
            if self._on_select:
                self._on_select(action)

        btn_st = ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=s(6)),
            padding=ft.padding.only(left=s(18), top=s(7), right=s(18), bottom=s(7)),
            text_style=ft.TextStyle(size=s(12), font_family=ff),
        )

        content = ft.Column([
            ft.Container(height=s(10)),
            ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, size=36, color=theme.warning),
            ft.Container(height=s(12)),
            ft.Text("确认操作", size=s(15), weight=ft.FontWeight.W_600,
                    color=theme.text_primary, font_family=ff),
            ft.Container(height=s(8)),
            ft.Container(
                ft.Text(message, size=s(12), color=theme.text_secondary, font_family=ff),
                padding=ft.padding.symmetric(horizontal=s(20)),
            ),
            ft.Container(height=s(20)),
            ft.Row([
                ft.OutlinedButton("取消", on_click=lambda e: dlg.close(),
                    style=ft.ButtonStyle(shape=btn_st.shape, padding=btn_st.padding,
                        text_style=btn_st.text_style,
                        side=ft.BorderSide(1, theme.border), color=theme.text_secondary)),
                ft.Container(width=s(10)),
                ft.ElevatedButton("确定", on_click=_do_confirm,
                    style=ft.ButtonStyle(shape=btn_st.shape, padding=btn_st.padding,
                        text_style=btn_st.text_style,
                        bgcolor=theme.error, color=ft.Colors.WHITE, elevation=0)),
            ], spacing=0, tight=True, alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(height=s(10)),
        ], spacing=0, tight=True, alignment=ft.MainAxisAlignment.CENTER,
           horizontal_alignment=ft.CrossAxisAlignment.CENTER)

        dlg = ModalDialog(page, content, width=400, height=220)
        dlg.open()

    def show(self, page, x: float, y: float):
        """在 (x, y) 位置弹出菜单，下方空间不足时自动向上弹出。"""
        global _current_menu
        close_current_menu()

        # 防御性清理：遍历 overlay 移除所有残留的菜单容器
        # （启动卡顿期间事件排队可能导致 page.overlay.remove 未能生效）
        for item in list(page.overlay):
            if isinstance(item, ft.Container) and id(item) in _menu_containers:
                try:
                    page.overlay.remove(item)
                except (ValueError, AssertionError):
                    pass

        self._page = page
        pw, ph = page.width, page.height

        # 估算菜单高度：每项 ~36px + 分割线 ~12px + 内边距 8px
        item_count = sum(1 for _ in self._menu_col.controls
                         if not isinstance(_, ft.Divider))
        divider_count = sum(1 for _ in self._menu_col.controls
                           if isinstance(_, ft.Divider))
        est_h = item_count * 36 + divider_count * 12 + 8

        # 水平边缘钳制
        menu_x = min(max(x, 4), pw - self.MENU_W - 8)
        # 垂直方向：下方空间不足则向上弹出
        menu_y = (y - est_h - 4) if (y + est_h > ph - 8) else (y - 10)
        menu_y = max(4, menu_y)

        self._container.left = menu_x
        self._container.top = menu_y
        self._container.opacity = 0  # 初始透明，下一帧渐入

        self._overlay = self._container
        page.overlay.append(self._container)
        _current_menu = self
        page.update()
        # 渐入动画
        self._container.opacity = 1
        page.update()
