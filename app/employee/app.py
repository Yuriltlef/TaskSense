"""员工子进程窗口应用 — Flet 窗口 + 登录/工作台视图切换."""

import sys
import os
import threading
import flet as ft

from app.config.theme import theme, SCALE, s
from app.core.services.employee_service import employee_service
from app.core.state import state
from app.core.services.socket_client import SocketClient
from app.employee.pages.login_page import LoginPage
from app.employee.pages.workbench_page import WorkbenchPage


class EmployeeWindowApp:
    """员工独立窗口应用。

    管理三个视图：
    - ConnectingView（正在连接主应用）
    - LoginPage（登录/选择员工）
    - WorkbenchPage（任务列表 + 接单/提交）

    连接在后台线程执行，UI 先渲染避免空白窗口。
    """

    def __init__(self):
        self.page: ft.Page | None = None
        self._current_employee_id: str = ""
        self._current_employee_name: str = ""
        self._body: ft.Container | None = None
        self._inner: ft.Container | None = None
        self._login_page: LoginPage | None = None
        self._workbench_page: WorkbenchPage | None = None
        self._client: SocketClient | None = None
        self._title_text: ft.Text | None = None
        self._title_bar: ft.Container | None = None
        self._max_btn: ft.IconButton | None = None
        self._last_maximized: bool | None = None

    # ── Flet 入口 ──

    def main(self, page: ft.Page):
        self.page = page
        self._setup_window()
        self._setup_fonts()
        self._setup_icon()
        self._create_ui()          # ① 先渲染 UI（标题栏 + body 槽位）
        self._show_connecting()    # ② 显示"正在连接"
        page.on_resized = self._on_window_resized
        page.update()
        self._connect_async()      # ③ 后台连接，连上后切到登录页
        employee_service.load()

    # ── 窗口设置 ──

    def _setup_window(self):
        self.page.title = "TaskSense - 员工工作台"
        self.page.theme_mode = ft.ThemeMode.DARK

        # 无边框样式 — 与主应用一致
        self.page.window.frameless = False
        self.page.window.title_bar_hidden = True
        self.page.window.title_bar_buttons_hidden = True
        self.page.window.bgcolor = ft.Colors.TRANSPARENT
        self.page.window.on_close = lambda e: self._on_window_close()

        self.page.window.width = round(1000 * SCALE)
        self.page.window.height = round(700 * SCALE)
        self.page.window.min_width = round(600 * SCALE)
        self.page.window.min_height = round(400 * SCALE)
        self.page.padding = 0
        self.page.spacing = 0
        self.page.margin = 0
        self.page.bgcolor = ft.Colors.TRANSPARENT

    def _on_window_close(self):
        if self._client:
            self._client.stop_polling()
            self._client.close()

    def _setup_fonts(self):
        fonts_dir = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "..", "resources"))
        self.page.fonts = {
            theme.font_family: os.path.join(
                fonts_dir, "HarmonyOS_Sans_SC_Medium.ttf"),
            theme.font_family_bold: os.path.join(
                fonts_dir, "HarmonyOS_Sans_SC_Bold.ttf"),
        }

    def _setup_icon(self):
        icon_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "..", "resources", "concept_paperplane.ico"))
        self.page.window.icon = icon_path

    # ── 连接（后台线程）──

    def _show_connecting(self):
        """显示"正在连接"状态——UI 先渲染，不等网络。"""
        ff = theme.font_family
        self._body.content = ft.Container(
            ft.Column([
                ft.Container(height=s(60)),
                ft.ProgressRing(width=s(32), height=s(32), color=theme.info),
                ft.Container(height=s(16)),
                ft.Text("正在连接主应用...", size=s(14),
                        color=theme.text_primary, font_family=ff),
                ft.Container(height=s(4)),
                ft.Text("如果持续无法连接，请确保主应用已启动",
                        size=s(11), color=theme.text_secondary, font_family=ff),
            ], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            expand=True, alignment=ft.alignment.center, bgcolor=theme.bg,
        )

    def _show_connect_error(self, error: str):
        """显示连接失败状态。"""
        ff = theme.font_family
        self._body.content = ft.Container(
            ft.Column([
                ft.Container(height=s(60)),
                ft.Icon(ft.Icons.CLOUD_OFF, size=s(36), color=theme.error),
                ft.Container(height=s(12)),
                ft.Text("无法连接主应用", size=s(14), weight=ft.FontWeight.W_600,
                        color=theme.error, font_family=ff),
                ft.Container(height=s(6)),
                ft.Text(error, size=s(11), color=theme.text_secondary, font_family=ff),
                ft.Container(height=s(16)),
                ft.ElevatedButton("重试", icon=ft.Icons.REFRESH,
                    style=ft.ButtonStyle(
                        bgcolor=theme.info, color=ft.Colors.WHITE,
                        shape=ft.RoundedRectangleBorder(radius=s(6))),
                    on_click=lambda e: self._retry_connect()),
            ], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            expand=True, alignment=ft.alignment.center, bgcolor=theme.bg,
        )

    def _retry_connect(self):
        """重试连接。"""
        self._show_connecting()
        self._body.update()
        self._connect_async()

    def _connect_async(self):
        """后台线程：连接主进程 socket → 获取状态 → 切换到登录页。"""

        def _do_connect():
            try:
                client = SocketClient(tag="employee")
                state_dict = client.get_state()
                state.load_from_dict(state_dict)
                client.start_polling(
                    interval=1.0,
                    on_change=self._on_external_change,
                    on_disconnect=lambda: self._do_close(),
                )
                self._client = client
                # 切回主线程更新 UI
                self.page.run_task(self._on_connected)
            except Exception as e:
                self.page.run_task(self._on_connect_failed, str(e))

        threading.Thread(target=_do_connect, daemon=True).start()

    async def _on_connected(self):
        """连接成功回调（主线程）——切换到登录页。"""
        self.show_login()
        self._body.update()

    async def _on_connect_failed(self, error: str):
        """连接失败回调（主线程）——显示错误页。"""
        self._show_connect_error(error)
        self._body.update()

    # ── UI 结构 ──

    def _create_ui(self):
        ff = theme.font_family
        H = s(34)
        icon_sz = s(16)
        btn_w = s(36)

        # ── 窗口按钮工厂（与主应用 win_btn 一致）──
        def win_btn(icon, on_click, tooltip, hover_color=ft.Colors.GREY_800):
            return ft.IconButton(
                icon=icon, icon_size=icon_sz, icon_color=ft.Colors.WHITE,
                width=btn_w, height=H,
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.TRANSPARENT,
                    overlay_color=hover_color,
                    shape=ft.RoundedRectangleBorder(radius=0),
                ),
                mouse_cursor=ft.MouseCursor.BASIC,
                tooltip=ft.Tooltip(message=tooltip, bgcolor=theme.tooltip_bg,
                                   text_style=ft.TextStyle(
                                       color=ft.Colors.WHITE, font_family=ff)),
                on_click=on_click,
            )

        # ── 最大化按钮（动态图标）──
        def make_max_btn():
            if self.page and self.page.window.maximized:
                return win_btn(ft.Icons.FULLSCREEN_EXIT, self._maximize, "还原")
            return win_btn(ft.Icons.CROP_SQUARE, self._maximize, "最大化")

        self._max_btn = make_max_btn()

        # ── 拖拽区域 ──
        drag_area = ft.WindowDragArea(
            ft.GestureDetector(
                content=ft.Container(expand=True),
                mouse_cursor=ft.MouseCursor.BASIC,
                on_double_tap=self._on_title_double_tap,
                on_hover=self._on_title_hover,
            ),
            expand=True,
        )

        # ── 标题文本 ──
        self._title_text = ft.Text(
            "员工工作台 - 请登录", size=s(12),
            color=theme.text_secondary, font_family=ff,
        )

        # ── 组装标题栏 ──
        bar_row = ft.Row([
            ft.Container(width=s(8)),
            ft.Image(src=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "resources", "concept_paperplane.ico")), width=s(18), height=s(18), fit=ft.ImageFit.CONTAIN),
            ft.Container(width=s(10)),
            ft.Icon(ft.Icons.PERSON_OUTLINE, size=s(15), color=theme.info),
            ft.Container(width=s(6)),
            ft.Container(content=self._title_text),
            drag_area,
            win_btn(ft.Icons.REMOVE, self._minimize, "最小化"),
            self._max_btn,
            win_btn(ft.Icons.CLOSE, lambda e: self._do_close(),
                    "关闭", hover_color=ft.Colors.RED_900),
        ], spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER)

        self._title_bar = ft.Container(
            content=bar_row,
            height=H,
            bgcolor=theme.surface,
            border=ft.border.only(
                bottom=ft.BorderSide(1, ft.Colors.with_opacity(0.10, ft.Colors.WHITE))),
        )

        # 内容 body（视图在这里切换）
        self._body = ft.Container(expand=True, bgcolor=theme.bg)

        self._inner = ft.Container(
            content=ft.Column([
                self._title_bar,
                ft.Divider(height=1, color=theme.border),
                self._body,
            ], spacing=0, tight=True, expand=True),
            bgcolor=theme.bg,
            expand=True,
        )

        self.page.add(ft.Container(
            content=self._inner,
            bgcolor=ft.Colors.TRANSPARENT,
            expand=True,
        ))

    # ── 视图切换 ──

    def show_login(self):
        """切换到登录页。"""
        self._current_employee_id = ""
        self._current_employee_name = ""
        self._workbench_page = None

        self._login_page = LoginPage(
            self.page,
            on_login=lambda eid, ename: self.show_workbench(eid, ename),
        )
        self._body.content = self._login_page.build()
        self._title_text.value = "员工工作台 - 请登录"
        try:
            self._title_text.update()
        except Exception:
            pass
        self._body.update()

    def show_workbench(self, employee_id: str, employee_name: str):
        """切换到工作台页。"""
        self._current_employee_id = employee_id
        self._current_employee_name = employee_name

        # 确保 state 中有正确的员工身份
        from app.core.state import state as app_state
        app_state.current_employee_id = employee_id
        app_state.current_employee_name = employee_name

        self._workbench_page = WorkbenchPage(
            self.page,
            employee_id,
            employee_name,
            self._client,
            on_switch=lambda: self.show_login(),
        )
        self._body.content = self._workbench_page.build()
        self._title_text.value = f"员工工作台 - {employee_name}"
        try:
            self._title_text.update()
        except Exception:
            pass
        self._body.update()

    # ── 外部变更回调 ──

    def _on_external_change(self):
        """状态变更 → 拉取最新数据 → 刷新工作台。"""
        if not self._client:
            return
        try:
            state_dict = self._client.get_state()
            state.load_from_dict(state_dict)
        except Exception:
            return
        if self._current_employee_id and self._workbench_page:
            self._workbench_page.refresh()

    # ── 窗口操作（与主应用一致）──

    def _on_window_resized(self, e):
        """窗口大小变化时检测最大化状态（响应 Win+↑ / 拖拽顶部等外部操作）。"""
        current = self.page.window.maximized
        if current != self._last_maximized:
            self._last_maximized = current
            self._update_maximize_button()

    def _on_title_hover(self, e):
        """标题栏悬停时检测最大化状态变化。"""
        current = self.page.window.maximized
        if current != self._last_maximized:
            self._last_maximized = current
            self._update_maximize_button()

    def _on_title_double_tap(self, e):
        """双击标题栏切换最大化/还原。"""
        self.page.window.maximized = not self.page.window.maximized
        self.page.update()
        self._update_maximize_button()

    def _update_maximize_button(self):
        """刷新最大化按钮图标。"""
        if not self._title_bar:
            return
        self._last_maximized = self.page.window.maximized
        bar_row = self._title_bar.content
        new_ctrls = list(bar_row.controls)
        # 窗口按钮在最后 3 个：最小化、最大化、关闭
        max_idx = len(new_ctrls) - 2
        H = s(34); icon_sz = s(16); btn_w = s(36)
        ff = theme.font_family

        def win_btn(icon, on_click, tooltip, hover_color=ft.Colors.GREY_800):
            return ft.IconButton(
                icon=icon, icon_size=icon_sz, icon_color=ft.Colors.WHITE,
                width=btn_w, height=H,
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.TRANSPARENT,
                    overlay_color=hover_color,
                    shape=ft.RoundedRectangleBorder(radius=0),
                ),
                mouse_cursor=ft.MouseCursor.BASIC,
                tooltip=ft.Tooltip(message=tooltip, bgcolor=theme.tooltip_bg,
                                   text_style=ft.TextStyle(
                                       color=ft.Colors.WHITE, font_family=ff)),
                on_click=on_click,
            )

        if self.page.window.maximized:
            new_ctrls[max_idx] = win_btn(
                ft.Icons.FULLSCREEN_EXIT, self._maximize, "还原")
        else:
            new_ctrls[max_idx] = win_btn(
                ft.Icons.CROP_SQUARE, self._maximize, "最大化")
        bar_row.controls = new_ctrls
        self._title_bar.update()

    def _minimize(self, e=None):
        self.page.window.minimized = True
        self.page.update()

    def _maximize(self, e=None):
        self.page.window.maximized = not self.page.window.maximized
        self.page.update()
        self._update_maximize_button()

    def _do_close(self):
        """关闭窗口（由 socket 断开触发，在 poll 线程内调用）。"""
        self._client = None
        self.page.window.close()
