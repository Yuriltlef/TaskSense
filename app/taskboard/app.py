"""任务看板独立窗口应用 — 只读看板视图."""

import os
import threading
import flet as ft

from app.config.theme import theme, SCALE, s
from app.core.state import state
from app.core.services.socket_client import SocketClient

_PRI_COLORS = {
    "aog": "#f44747", "cat_a": "#e88400", "cat_b": "#e0b800",
    "cat_c": "#5294e2", "cat_d": "#808080",
}
_COLUMN_IDS = ["scheduled", "ready", "in_progress", "inspection", "parts_hold", "completed"]
_COLUMN_TITLES = {"scheduled": "已排程", "ready": "就绪", "in_progress": "执行中",
                   "inspection": "验收中", "parts_hold": "阻塞中", "completed": "已完成"}


class TaskBoardWindowApp:

    def __init__(self):
        self.page: ft.Page | None = None
        self._body: ft.Container | None = None
        self._client: SocketClient | None = None
        self._title_bar: ft.Container | None = None
        self._max_btn: ft.IconButton | None = None
        self._last_maximized: bool | None = None
        self._board: ft.Row | None = None
        self._title_text: ft.Text | None = None

    def main(self, page: ft.Page):
        self.page = page
        self._setup_window()
        self._setup_fonts()
        self._create_ui()          # 先渲染 UI
        self._show_connecting()    # 显示"正在连接"
        page.on_resized = self._on_window_resized
        page.update()
        self._connect_async()      # 后台连接

    def _setup_window(self):
        self.page.title = "TaskSense - 任务看板"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.window.frameless = False
        self.page.window.title_bar_hidden = True
        self.page.window.title_bar_buttons_hidden = True
        self.page.window.bgcolor = ft.Colors.TRANSPARENT
        self.page.window.on_close = lambda e: self._on_window_close()
        self.page.window.width = round(1300 * SCALE)
        self.page.window.height = round(750 * SCALE)
        self.page.window.min_width = round(800 * SCALE)
        self.page.window.min_height = round(450 * SCALE)
        self.page.padding = 0; self.page.spacing = 0; self.page.margin = 0
        self.page.bgcolor = ft.Colors.TRANSPARENT

    def _setup_fonts(self):
        fonts_dir = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "..", "sources"))
        self.page.fonts = {
            theme.font_family: os.path.join(fonts_dir, "HarmonyOS_Sans_SC_Medium.ttf"),
            theme.font_family_bold: os.path.join(fonts_dir, "HarmonyOS_Sans_SC_Bold.ttf"),
        }

    # ── 连接（后台线程）──

    def _show_connecting(self):
        ff = theme.font_family
        self._body.content = ft.Container(
            ft.Column([
                ft.Container(height=s(60)),
                ft.ProgressRing(width=s(32), height=s(32), color=theme.info),
                ft.Container(height=s(16)),
                ft.Text("正在连接主应用...", size=s(14),
                        color=theme.text_primary, font_family=ff),
            ], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            expand=True, alignment=ft.alignment.center, bgcolor=theme.bg,
        )

    def _show_connect_error(self, error: str):
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
        self._show_connecting()
        self._body.update()
        self._connect_async()

    def _connect_async(self):
        def _do_connect():
            try:
                client = SocketClient(tag="taskboard")
                state_dict = client.get_state()
                state.load_from_dict(state_dict)
                client.start_polling(
                    interval=1.0,
                    on_change=self._refresh,
                    on_disconnect=lambda: self._do_close(),
                )
                self._client = client
                self.page.run_task(self._on_connected)
            except Exception as e:
                self.page.run_task(self._on_connect_failed, str(e))

        threading.Thread(target=_do_connect, daemon=True).start()

    async def _on_connected(self):
        self._body.content = self._board
        self._refresh(pull=False)  # state 已由 connect_async 加载
        self._body.update()

    async def _on_connect_failed(self, error: str):
        self._show_connect_error(error)
        self._body.update()

    def _on_window_close(self):
        if self._client:
            self._client.stop_polling()
            self._client.close()

    # ── UI ──

    def _create_ui(self):
        ff = theme.font_family; H = s(34); icon_sz = s(16); btn_w = s(36)

        def win_btn(icon, on_click, tooltip, hover_color=ft.Colors.GREY_800):
            return ft.IconButton(
                icon=icon, icon_size=icon_sz, icon_color=ft.Colors.WHITE,
                width=btn_w, height=H,
                style=ft.ButtonStyle(bgcolor=ft.Colors.TRANSPARENT,
                                     overlay_color=hover_color,
                                     shape=ft.RoundedRectangleBorder(radius=0)),
                mouse_cursor=ft.MouseCursor.BASIC, on_click=on_click)

        def make_max_btn():
            if self.page and self.page.window.maximized:
                return win_btn(ft.Icons.FULLSCREEN_EXIT, self._maximize, "还原")
            return win_btn(ft.Icons.CROP_SQUARE, self._maximize, "最大化")

        self._max_btn = make_max_btn()

        drag_area = ft.WindowDragArea(ft.GestureDetector(
            content=ft.Container(expand=True), mouse_cursor=ft.MouseCursor.BASIC,
            on_double_tap=self._on_title_double_tap, on_hover=self._on_title_hover),
            expand=True)

        self._title_text = ft.Text("任务看板", size=s(12), color=theme.text_secondary, font_family=ff)

        bar_row = ft.Row([
            ft.Container(width=s(8)),
            ft.Text("✈", size=s(15), font_family=ff),
            ft.Container(width=s(6)),
            ft.Icon(ft.Icons.VIEW_COLUMN, size=s(15), color=theme.info),
            ft.Container(width=s(6)),
            ft.Container(content=self._title_text),
            drag_area,
            win_btn(ft.Icons.REMOVE, self._minimize, "最小化"),
            self._max_btn,
            win_btn(ft.Icons.CLOSE, lambda e: self._do_close(), "关闭", hover_color=ft.Colors.RED_900),
        ], spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER)

        self._title_bar = ft.Container(content=bar_row, height=H, bgcolor=theme.surface,
            border=ft.border.only(bottom=ft.BorderSide(1, ft.Colors.with_opacity(0.10, ft.Colors.WHITE))))

        self._board = ft.Row([], spacing=s(8), expand=True,
            scroll=ft.ScrollMode.HIDDEN, vertical_alignment=ft.CrossAxisAlignment.START)

        self._body = ft.Container(expand=True, bgcolor=theme.bg,
            padding=ft.padding.all(s(12)))

        self.page.add(ft.Container(content=ft.Column([
            self._title_bar, ft.Divider(height=1, color=theme.border), self._body,
        ], spacing=0, tight=True, expand=True), bgcolor=ft.Colors.TRANSPARENT, expand=True))

    # ── 数据刷新 ──

    def _refresh(self, pull: bool = True):
        if pull and self._client:
            try:
                state_dict = self._client.get_state()
                state.load_from_dict(state_dict)
            except Exception:
                return
        ff = theme.font_family

        col_width = max(s(160), (self.page.width - s(40)) // len(_COLUMN_IDS))
        columns = []

        total = 0
        for cid in _COLUMN_IDS:
            tasks = [t for t in state.get_all_tasks() if t.status.value == cid]
            total += len(tasks)
            cards = []
            if tasks:
                for t in tasks:
                    pri_color = _PRI_COLORS.get(t.priority.value, "#5294e2")
                    cards.append(ft.Container(
                        ft.Column([
                            ft.Row([
                                ft.Container(width=s(3), height=s(24), bgcolor=pri_color,
                                             border_radius=s(2)),
                                ft.Container(width=s(6)),
                            ft.Text(t.title[:20], size=s(13), color=theme.text_primary,
                                    font_family=ff, max_lines=2, expand=True),
                            ], spacing=0),
                            ft.Container(height=s(4)),
                            ft.Row([
                            ft.Text(t.priority.value.upper(), size=s(11),
                                    color=pri_color, font_family=ff),
                            ft.Container(width=s(8)),
                            ft.Text(t.employee_name or "", size=s(11),
                                    color=theme.text_secondary, font_family=ff),
                                ft.Container(expand=True),
                            ]),
                        ft.Text(t.ata_chapter or "", size=s(11),
                                color=theme.text_disabled, font_family=ff),
                        ], spacing=0, tight=True),
                        bgcolor=theme.card, border_radius=s(6),
                        border=ft.border.all(1, theme.border),
                        padding=ft.padding.all(s(10)),
                        margin=ft.padding.only(bottom=s(6)),
                    ))

            col_header = ft.Container(
                ft.Row([
                ft.Text(_COLUMN_TITLES.get(cid, cid), size=s(14),
                        weight=ft.FontWeight.W_600, color=theme.text_primary, font_family=ff),
                ft.Container(width=s(6)),
                ft.Container(ft.Text(str(len(tasks)), size=s(12), color=theme.text_secondary,
                                     font_family=ff),
                                 bgcolor=theme.border_active, border_radius=s(10),
                                 padding=ft.padding.symmetric(horizontal=s(8), vertical=s(2))),
                ]),
                padding=ft.padding.only(bottom=s(8), left=s(4)))

            columns.append(ft.Container(
                ft.Column([col_header, ft.ListView(cards, expand=True, spacing=0)],
                          spacing=0, tight=True, expand=True),
                width=col_width, expand=True,
                bgcolor=theme.surface, border_radius=s(8),
                padding=ft.padding.all(s(10)),
                border=ft.border.all(1, theme.border),
            ))

        self._title_text.value = f"任务看板  -  {total} 个任务"
        self._board.controls = columns
        try: self._board.update()
        except: pass

    # ── 窗口操作 ──

    def _on_window_resized(self, e):
        current = self.page.window.maximized
        if current != self._last_maximized:
            self._last_maximized = current
            self._update_maximize_button()
        self._refresh()

    def _on_title_hover(self, e):
        current = self.page.window.maximized
        if current != self._last_maximized:
            self._last_maximized = current
            self._update_maximize_button()

    def _on_title_double_tap(self, e):
        self.page.window.maximized = not self.page.window.maximized
        self.page.update()
        self._update_maximize_button()

    def _update_maximize_button(self):
        if not self._title_bar: return
        self._last_maximized = self.page.window.maximized
        bar_row = self._title_bar.content
        new_ctrls = list(bar_row.controls)
        max_idx = len(new_ctrls) - 2
        H = s(34); icon_sz = s(16); btn_w = s(36)

        def _wbtn(icon):
            return ft.IconButton(
                icon=icon, icon_size=icon_sz, icon_color=ft.Colors.WHITE,
                width=btn_w, height=H,
                style=ft.ButtonStyle(bgcolor=ft.Colors.TRANSPARENT,
                                     overlay_color=ft.Colors.GREY_800,
                                     shape=ft.RoundedRectangleBorder(radius=0)),
                mouse_cursor=ft.MouseCursor.BASIC, on_click=self._maximize)

        if self.page.window.maximized:
            new_ctrls[max_idx] = _wbtn(ft.Icons.FULLSCREEN_EXIT)
        else:
            new_ctrls[max_idx] = _wbtn(ft.Icons.CROP_SQUARE)
        bar_row.controls = new_ctrls
        self._title_bar.update()

    def _minimize(self, e=None): self.page.window.minimized = True; self.page.update()
    def _maximize(self, e=None): self.page.window.maximized = not self.page.window.maximized; self.page.update(); self._update_maximize_button()
    def _do_close(self):
        """关闭窗口（由 socket 断开触发，在 poll 线程内调用）。"""
        self._client = None
        self.page.window.close()
