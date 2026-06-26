"""右键菜单."""
from __future__ import annotations

import flet as ft
from app.config.theme import theme


class ContextMenu(ft.AlertDialog):
    def __init__(self, items: list[dict], on_select=None):
        self._on_select = on_select
        ff = theme.font_family
        menu = []
        for item in items:
            if item.get("divider"):
                menu.append(ft.Divider(height=1, color=theme.border))
                continue
            c = item.get("color", theme.text_primary)
            menu.append(ft.TextButton(
                content=ft.Row([
                    ft.Icon(item.get("icon", ft.Icons.CHEVRON_RIGHT),
                            size=theme.font_lg, color=c),
                    ft.Text(item["label"], size=theme.font_sm, color=c, font_family=ff),
                ], spacing=theme.pad_sm),
                style=ft.ButtonStyle(
                    bgcolor={"hovered": theme.card_hover},
                    padding=ft.padding.only(left=theme.pad_md, top=theme.pad_sm,
                                            right=theme.pad_md, bottom=theme.pad_sm),
                ),
                on_click=lambda e, a=item["action"]: self._pick(a),
            ))
        super().__init__(
            content=ft.Column(menu, spacing=2, width=round(200*1.5)),
            bgcolor=theme.surface,
            shape=ft.RoundedRectangleBorder(radius=theme.radius_md),
            content_padding=ft.padding.only(top=4, bottom=4),
        )

    def _pick(self, action):
        self.open = False
        if self._on_select: self._on_select(action)

    def show(self, page):
        page.dialog = self; self.open = True; page.update()
