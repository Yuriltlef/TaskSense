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


# ═══════════════════════════════════════════
# 共享表单字段工厂（_dlg_schedule / _dlg_edit 复用）──
# ═══════════════════════════════════════════

def make_field(hint="", width=None, readonly=False, value="", **kw) -> ft.TextField | ft.Text:
    """统一 TextField 工厂。readonly=True 时返回纯 Text。"""
    ff = theme.font_family
    if readonly:
        return ft.Text(str(value or "—"), size=s(13),
                       color=theme.text_disabled, font_family=ff)
    tf = ft.TextField(
        hint_text=hint, value=str(value or ""),
        border_color=theme.border, focused_border_color=theme.info,
        cursor_color=theme.info,
        text_style=ft.TextStyle(color="#e0e0e0", size=s(13), font_family=ff),
        hint_style=ft.TextStyle(color=theme.text_secondary, size=s(12), font_family=ff),
        bgcolor=theme.card, dense=True, border_radius=s(6),
        content_padding=ft.padding.only(left=s(10), top=s(8), right=s(10), bottom=s(8)),
        width=width,
        **kw,
    )
    return tf


def make_label(text: str, required: bool = False) -> ft.Text:
    """统一标签工厂。required=True 时末尾加红色 *。"""
    ff = theme.font_family
    if required:
        return ft.Text(spans=[
            ft.TextSpan(text, ft.TextStyle(color=theme.text_primary, size=s(12),
                        font_family=ff, weight=ft.FontWeight.W_500)),
            ft.TextSpan(" *", ft.TextStyle(color=theme.error, size=s(12),
                        font_family=ff, weight=ft.FontWeight.W_500))])
    return ft.Text(text, size=s(12), color=theme.text_primary,
                   font_family=ff, weight=ft.FontWeight.W_500)


def make_col(label: ft.Text, ctrl) -> ft.Column:
    """标签 + 控件的 Column 包装。"""
    return ft.Column([label, ctrl], spacing=s(4), tight=True, expand=True)


def clamp_time_field(tf: ft.TextField, max_val: int):
    """校验时/分输入范围（blur 事件回调）。"""
    val = (tf.value or "").strip()
    if val:
        if not val.isdigit():
            tf.value = ""
        else:
            n = int(val)
            if n > max_val:
                tf.value = str(max_val)


def build_datetime(date_state: dict, h_f: ft.TextField,
                   m_f: ft.TextField):
    """从日期状态 + 时/分字段构建 datetime。"""
    from datetime import datetime as dt
    d = date_state.get("date")
    if not d:
        return None
    h = (h_f.value or "").strip()
    m = (m_f.value or "").strip()
    if h and m:
        try:
            return dt(d.year, d.month, d.day, int(h), int(m))
        except (ValueError, TypeError):
            pass
    return d

def make_date_picker(page, initial_date=None, locked: bool = False,
                    on_pick_callback=None) -> tuple:
    """统一日期选择器工厂。

    返回 (ctrl, state_dict, set_err_fn, clear_err_fn)。
    state_dict["date"] 存储选中的日期。
    """
    from datetime import datetime as dt
    ff = theme.font_family
    state = {"date": initial_date}
    dp = ft.DatePicker(
        first_date=dt(2024, 1, 1), last_date=dt(2030, 12, 31),
        on_change=lambda e: _on_pick(e))

    if initial_date:
        display = ft.Text(initial_date.strftime("%Y-%m-%d"), size=s(12),
                          color="#e0e0e0", font_family=ff)
    elif locked:
        display = ft.Text("—", size=s(12), color=theme.text_secondary,
                          font_family=ff)
    else:
        display = ft.Text("点击选择日期", size=s(12),
                          color=theme.text_secondary, font_family=ff)

    ctrl = ft.Container(
        content=ft.Row([
            ft.Icon(ft.Icons.CALENDAR_TODAY_OUTLINED, size=s(14),
                    color=theme.text_secondary),
            display,
        ], spacing=s(6)),
        bgcolor=theme.card, border_radius=s(6),
        border=ft.border.all(1, theme.border),
        padding=ft.padding.only(left=s(10), top=s(8), right=s(10), bottom=s(8)),
        on_click=None if locked else (lambda e: page.open(dp)),
        ink=not locked,
    )

    def _on_pick(e):
        if e.control.value:
            state["date"] = e.control.value
            display.value = state["date"].strftime("%Y-%m-%d")
            display.color = "#e0e0e0"
            ctrl.update()
            if on_pick_callback:
                on_pick_callback()

    def _set_err(msg):
        display.value = msg
        display.color = theme.error
        ctrl.border = ft.border.all(1, theme.error)
        ctrl.update()

    def _clear_err():
        if state["date"]:
            display.value = state["date"].strftime("%Y-%m-%d")
            display.color = "#e0e0e0"
        else:
            display.value = "点击选择日期"
            display.color = theme.text_secondary
        ctrl.border = ft.border.all(1, theme.border)
        ctrl.update()

    return ctrl, state, _set_err, _clear_err


# ── dialog_builder 公开 API ──
__all__ = [
    "button_style", "header", "footer",
    "make_field", "make_label", "make_col",
    "clamp_time_field", "build_datetime",
]
