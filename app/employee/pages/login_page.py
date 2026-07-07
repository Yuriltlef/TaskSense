"""登录页 — 输入员工姓名和 ID 登录."""

import flet as ft

from app.config.theme import theme, s
from app.core.services.employee_service import employee_service
from app.ui.widgets.toast import Toast


class LoginPage:
    """员工登录页面（独立窗口内的状态 A）。

    用法:
        login = LoginPage(page, on_login=lambda eid, ename: ...)
        container = login.build()
    """

    def __init__(self, page: ft.Page, on_login):
        self._page = page
        self._on_login = on_login  # callback(eid, ename)
        self._name_field: ft.TextField | None = None
        self._id_field: ft.TextField | None = None

    def build(self) -> ft.Container:
        ff = theme.font_family

        field_style = dict(
            border_color=theme.border,
            focused_border_color=theme.info,
            bgcolor=theme.card_hover,
            text_style=ft.TextStyle(color=theme.form_text, size=s(14), font_family=ff),
            hint_style=ft.TextStyle(color=theme.text_disabled, size=s(12), font_family=ff),
            border_radius=s(6),
            content_padding=ft.padding.symmetric(horizontal=s(12), vertical=s(10)),
            dense=True,
        )

        self._id_field = ft.TextField(
            hint_text="请输入员工 ID（如 ZH001）",
            autofocus=True,
            on_submit=lambda e: self._name_field.focus(),
            **field_style,
        )
        self._name_field = ft.TextField(
            hint_text="请输入员工姓名",
            on_submit=lambda e: self._on_confirm(),
            **field_style,
        )

        tip = ft.Text(
            "请输入您的员工 ID 和姓名以登录工作台",
            size=s(11), color=theme.text_secondary, font_family=ff,
            italic=True,
        )

        login_btn = ft.ElevatedButton(
            text="登录",
            icon=ft.Icons.LOGIN,
            style=ft.ButtonStyle(
                bgcolor=theme.info,
                color=ft.Colors.WHITE,
                shape=ft.RoundedRectangleBorder(radius=s(6)),
                padding=ft.padding.symmetric(horizontal=s(28), vertical=s(10)),
                text_style=ft.TextStyle(size=s(14), font_family=ff),
            ),
            on_click=lambda e: self._on_confirm(),
        )

        return ft.Container(
            content=ft.Column([
                ft.Container(expand=True),
                ft.Icon(ft.Icons.BADGE_OUTLINED, size=s(40), color=theme.border_active),
                ft.Container(height=s(8)),
                ft.Text("员工工作台登录", size=s(18), weight=ft.FontWeight.W_600,
                        color=theme.text_primary, font_family=ff),
                ft.Container(height=s(4)),
                tip,
                ft.Container(height=s(16)),
                ft.Container(content=self._id_field, width=340),
                ft.Container(height=s(10)),
                ft.Container(content=self._name_field, width=340),
                ft.Container(height=s(16)),
                login_btn,
                ft.Container(expand=True),
            ], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            expand=True,
            bgcolor=theme.bg,
            padding=ft.padding.all(s(16)),
        )

    # ── 登录验证 ──

    def _on_confirm(self):
        name = (self._name_field.value or "").strip()
        emp_id = (self._id_field.value or "").strip().upper()

        if not name:
            Toast.show(self._page, "请输入员工姓名", "warning")
            return
        if not emp_id:
            Toast.show(self._page, "请输入员工 ID", "warning")
            return

        emp = employee_service.get_employee(emp_id)
        if not emp:
            Toast.show(self._page, f"员工 ID '{emp_id}' 不存在", "warning")
            return
        if emp["name"] != name:
            Toast.show(self._page, f"姓名与 ID 不匹配", "warning")
            return
        if not emp.get("available", True):
            Toast.show(self._page, "该员工当前不可用", "warning")
            return

        self._on_login(emp_id, emp["name"])
