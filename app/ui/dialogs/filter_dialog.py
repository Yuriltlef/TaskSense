# -*- coding: utf-8 -*-
"""筛选弹窗."""
import flet as ft
from app.config.theme import theme, s
from app.core.models.kanban import FilterState
from app.core.services.board_service import board_service
from app.ui.widgets.toast import Toast
from app.ui.components.modal_dialog import ModalDialog
from app.ui.services.dialog_builder import header as dlg_header, footer as dlg_footer


def open(page: ft.Page):
    ff = theme.font_family

    ata_dd = ft.Dropdown(
        dense=True,
        options=[ft.dropdown.Option(k, v) for k, v in [
            ("", "全部 ATA"), ("21", "21 - 空调"), ("24", "24 - 电源"),
            ("27", "27 - 飞行控制"), ("28", "28 - 燃油"), ("32", "32 - 起落架"),
            ("49", "49 - APU"), ("72", "72 - 发动机"), ("79", "79 - 滑油")]],
        border_color=theme.border, focused_border_color=theme.info,
        bgcolor=theme.card, border_radius=s(6),
        text_style=ft.TextStyle(color="#e0e0e0", size=s(12), font_family=ff),
    )
    pri_dd = ft.Dropdown(
        dense=True,
        options=[ft.dropdown.Option(k, v) for k, v in [
            ("", "全部优先级"), ("aog", "AOG"), ("cat_a", "Cat A"),
            ("cat_b", "Cat B"), ("cat_c", "Cat C")]],
        border_color=theme.border, focused_border_color=theme.info,
        bgcolor=theme.card, border_radius=s(6),
        text_style=ft.TextStyle(color="#e0e0e0", size=s(12), font_family=ff),
    )

    def _apply(_):
        f = FilterState()
        if ata_dd.value: f.ata_chapters = [ata_dd.value]
        if pri_dd.value: f.priorities = [pri_dd.value]
        board_service.set_filters(f)
        dlg.close()
        Toast.show(page, "筛选已应用", "info")

    def _clear(_):
        ata_dd.value = ""; pri_dd.value = ""
        ata_dd.update(); pri_dd.update()
        board_service.set_filters(FilterState())
        dlg.close()
        Toast.show(page, "筛选已清除", "info")

    form = ft.Container(
        ft.Column([
            ft.Text("ATA 章节", size=s(12), color=theme.text_primary,
                    font_family=ff, weight=ft.FontWeight.W_500),
            ata_dd,
            ft.Divider(height=s(14), color=ft.Colors.TRANSPARENT),
            ft.Text("优先级", size=s(12), color=theme.text_primary,
                    font_family=ff, weight=ft.FontWeight.W_500),
            pri_dd,
        ], spacing=s(4), tight=True),
        padding=ft.padding.only(left=s(14), top=s(14), right=s(14), bottom=s(14)),
    )
    content = ft.Column([
        dlg_header(ft.Icons.FILTER_ALT_OUTLINED, "筛选任务", lambda e: dlg.close()),
        form,
        dlg_footer("清除", "应用筛选", _apply, on_cancel=_clear),
    ], spacing=0, tight=True)
    dlg = ModalDialog(page, content, width=360)
    dlg.open()
