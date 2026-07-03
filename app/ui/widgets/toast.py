"""Toast 通知 — page.overlay Stack 模式（兼容 Flet 0.28.3）."""

import threading
import flet as ft
from app.config.theme import theme, s


class Toast:
    """顶部居中浮动消息，淡入淡出，3s 自动消失。"""

    DURATION = 3000  # 统一 3s

    @staticmethod
    def show(page, message, level="info", duration_ms=None):
        colors = {
            "info": theme.info, "success": theme.success,
            "warning": theme.warning, "critical": theme.error,
        }
        icons = {
            "info": ft.Icons.INFO_OUTLINE,
            "success": ft.Icons.CHECK_CIRCLE_OUTLINE,
            "warning": ft.Icons.WARNING_AMBER_OUTLINED,
            "critical": ft.Icons.ERROR_OUTLINE,
        }
        if duration_ms is None:
            duration_ms = Toast.DURATION

        c = colors.get(level, theme.info)
        ff = theme.font_family

        toast = ft.Container(
            ft.Row([
                ft.Icon(icons.get(level, ft.Icons.INFO_OUTLINE),
                        color=c, size=s(14)),
                ft.Text(message, size=s(12), color=theme.text_primary,
                        font_family=ff),
            ], spacing=s(8)),
            bgcolor=theme.surface,
            border=ft.border.all(1, c),
            border_radius=s(8),
            padding=ft.padding.symmetric(horizontal=s(14), vertical=s(10)),
            shadow=ft.BoxShadow(spread_radius=1, blur_radius=12, color="#00000066"),
            animate_opacity=ft.Animation(300, ft.AnimationCurve.EASE_OUT),
            opacity=0,
        )

        # Row 水平居中，不拉伸 toast 宽度
        wrapper = ft.Row(
            [toast],
            alignment=ft.MainAxisAlignment.CENTER,
            top=s(40),
            left=0,
            right=0,
        )

        page.overlay.append(wrapper)
        page.update()

        # 淡入
        toast.opacity = 1
        toast.update()

        # 自动消失：淡出 → 移除
        def _dismiss():
            try:
                toast.opacity = 0
                toast.update()
                threading.Timer(0.35, lambda: _remove()).start()
            except Exception:
                _remove()

        def _remove():
            try:
                page.overlay.remove(wrapper)
                page.update()
            except Exception:
                pass

        if duration_ms > 0:
            threading.Timer(duration_ms / 1000, _dismiss).start()
