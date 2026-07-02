# -*- coding: utf-8 -*-
"""全局通知气泡 — 右上角动画弹入，支持队列和多级别."""

import flet as ft
import threading
import time
from collections import deque

from app.config.theme import theme, s


class NotificationBubble:
    """非侵入式通知气泡（page.overlay Stack 定位）。"""

    _instance = None
    _queue = deque()
    _active = None
    _page = None
    _lock = threading.Lock()

    @classmethod
    def show(cls, page, message, level="info", duration_ms=None):
        """显示一条通知。level: info | success | warning | error."""
        cls._page = page
        dur = {"info": 3000, "success": 3000, "warning": 5000, "error": 0}
        if duration_ms is None:
            duration_ms = dur.get(level, 3000)

        item = {"message": message, "level": level, "duration_ms": duration_ms}
        with cls._lock:
            cls._queue.append(item)
        cls._drain()

    @classmethod
    def _drain(cls):
        if cls._active is not None:
            return  # already showing
        with cls._lock:
            if not cls._queue:
                return
            item = cls._queue.popleft()

        bubble = cls._build(item)
        cls._page.overlay.append(bubble)
        cls._page.update()
        cls._active = bubble

        # auto-dismiss
        dur = item["duration_ms"]
        if dur > 0:
            def _dismiss():
                time.sleep(dur / 1000)
                cls._remove(bubble)
            threading.Thread(target=_dismiss, daemon=True).start()

        # trigger next after animation
        def _next():
            time.sleep(0.35)
            cls._active = None
            cls._drain()
        threading.Thread(target=_next, daemon=True).start()

    @classmethod
    def _remove(cls, bubble):
        try:
            if bubble in cls._page.overlay:
                cls._page.overlay.remove(bubble)
                cls._page.update()
        except Exception:
            pass

    @classmethod
    def _build(cls, item):
        colors = {
            "info": (theme.info, ft.Icons.INFO_OUTLINE, "#0d2137"),
            "success": (theme.success, ft.Icons.CHECK_CIRCLE_OUTLINE, "#0d2614"),
            "warning": (theme.warning, ft.Icons.WARNING_AMBER_OUTLINED, "#2e2000"),
            "error": (theme.error, ft.Icons.ERROR_OUTLINE, "#2e0d0d"),
        }
        c, icon, bg = colors.get(item["level"], colors["info"])

        bubble = ft.Container(
            content=ft.Row([
                ft.Icon(icon, color=c, size=s(16)),
                ft.Text(item["message"], size=s(12), color=theme.text_primary,
                        font_family=theme.font_family),
                ft.Container(expand=True),
                ft.IconButton(
                    ft.Icons.CLOSE, icon_size=s(12), icon_color=theme.text_secondary,
                    style=ft.ButtonStyle(bgcolor=ft.Colors.TRANSPARENT,
                        overlay_color=ft.Colors.RED_900,
                        shape=ft.RoundedRectangleBorder(radius=s(4))),
                    on_click=lambda e: cls._remove(bubble),
                ),
            ], spacing=s(8)),
            padding=ft.padding.only(left=s(14), top=s(10), right=s(6), bottom=s(10)),
            bgcolor=bg,
            border_radius=s(8),
            border=ft.border.all(1, c),
            width=min(420, cls._page.width - s(40)) if cls._page else 420,
            right=s(20),
            top=s(20),
            shadow=ft.BoxShadow(spread_radius=1, blur_radius=12, color="#00000066"),
            animate_opacity=ft.Animation(300, "easeOut"),
            animate_offset=ft.Animation(300, "easeOut"),
            opacity=1.0,
        )
        return bubble
