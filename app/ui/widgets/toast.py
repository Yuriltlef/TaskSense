"""Toast 通知."""
import flet as ft
from app.config.theme import theme


class Toast:
    @staticmethod
    def show(page, message, level="info", duration_ms=None):
        colors = {"info": theme.info, "success": theme.success,
                  "warning": theme.warning, "critical": theme.error}
        icons = {"info": ft.Icons.INFO_OUTLINE, "success": ft.Icons.CHECK_CIRCLE_OUTLINE,
                 "warning": ft.Icons.WARNING_AMBER_OUTLINED, "critical": ft.Icons.ERROR_OUTLINE}
        dur = {"info": 3000, "success": 3000, "warning": 5000, "critical": 0}
        if duration_ms is None: duration_ms = dur.get(level, 3000)
        c = colors.get(level, theme.info)
        snack = ft.SnackBar(
            content=ft.Row([
                ft.Icon(icons.get(level, ft.Icons.INFO_OUTLINE), color=c,
                        size=theme.font_xl),
                ft.Text(message, size=theme.font_sm, color=theme.text_primary,
                        font_family=theme.font_family),
            ], spacing=theme.spacing_md),
            bgcolor=theme.surface,
            behavior=ft.SnackBarBehavior.FLOATING,
            margin=ft.margin.only(top=10, right=10),
            duration=duration_ms,
            show_close_icon=(level == "critical"),
        )
        page.snack_bar = snack
        snack.open = True
        page.update()
