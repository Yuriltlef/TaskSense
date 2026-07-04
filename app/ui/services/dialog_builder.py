# -*- coding: utf-8 -*-
"""弹窗工厂 — 统一的 header/footer/button 构建器。

消除 6 个弹窗中 ~240 行重复的 header/footer/ButtonStyle 代码。
"""

import flet as ft
from app.config.theme import theme, s


def button_style() -> ft.ButtonStyle:
    """所有弹窗按钮的统一样式。"""
    return ft.ButtonStyle(
        shape=ft.RoundedRectangleBorder(radius=s(6)),
        padding=ft.padding.only(left=s(18), top=s(7), right=s(18), bottom=s(7)),
        text_style=ft.TextStyle(size=s(12), font_family=theme.font_family),
    )


def header(icon: str, title: str, on_close, progress=None) -> ft.Container:
    """弹窗统一 header：图标 + 标题 + 可选进度圈 + 关闭按钮。"""
    row_controls = [
        ft.Icon(icon, size=s(15), color="#5294e2"),
        ft.Text(title, size=s(14), weight=ft.FontWeight.W_600,
                color=theme.text_primary, font_family=theme.font_family),
    ]
    if progress is not None:
        row_controls.append(progress)
    row_controls.append(ft.Container(expand=True))
    row_controls.append(
        ft.IconButton(ft.Icons.CLOSE, icon_size=s(16),
                      icon_color=theme.text_secondary,
                      style=ft.ButtonStyle(
                          bgcolor=ft.Colors.TRANSPARENT,
                          overlay_color=ft.Colors.RED_900,
                          shape=ft.RoundedRectangleBorder(radius=s(4))),
                      on_click=on_close),
    )
    return ft.Container(
        ft.Row(row_controls, spacing=s(8)),
        padding=ft.padding.only(left=s(14), top=s(8), right=s(6), bottom=s(8)),
        border=ft.border.only(bottom=ft.BorderSide(1, theme.border)),
    )


def footer(cancel_text: str, confirm_text: str, on_confirm,
           on_cancel=None, extra_buttons=None,
           confirm_color: str = "#5294e2") -> ft.Container:
    """弹窗统一 footer：左侧额外按钮 + 右侧取消/确认。"""
    bt_st = button_style()
    btns: list = extra_buttons or []
    btns.append(ft.Container(expand=True))
    if on_cancel:
        btns.append(ft.OutlinedButton(cancel_text, on_click=on_cancel,
            style=ft.ButtonStyle(
                shape=bt_st.shape, padding=bt_st.padding,
                text_style=bt_st.text_style,
                side=ft.BorderSide(1, theme.border),
                color=theme.text_secondary)))
    btns.append(ft.ElevatedButton(confirm_text, on_click=on_confirm,
        style=ft.ButtonStyle(
            shape=bt_st.shape, padding=bt_st.padding,
            text_style=bt_st.text_style,
            bgcolor=confirm_color, color=ft.Colors.WHITE, elevation=0)))
    return ft.Container(
        ft.Row(btns, spacing=s(8)),
        padding=ft.padding.only(left=s(14), top=s(8), right=s(14), bottom=s(10)),
        border=ft.border.only(top=ft.BorderSide(1, theme.border)),
    )
