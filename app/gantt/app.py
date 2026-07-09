"""甘特图独立窗口应用 — 已排程任务时间线视图."""

import os
import threading
import flet as ft
from datetime import datetime, timedelta

from app.config.theme import theme, SCALE, s
from app.core.state import state
from app.core.services.socket_client import SocketClient

_PRI_COLORS = {
    "aog": "#f44747", "cat_a": "#e88400", "cat_b": "#e0b800",
    "cat_c": "#5294e2", "cat_d": "#808080",
}


class GanttWindowApp:

    def __init__(self):
        self.page: ft.Page | None = None
        self._body: ft.Container | None = None
        self._client: SocketClient | None = None
        self._title_bar: ft.Container | None = None
        self._max_btn: ft.IconButton | None = None
        self._last_maximized: bool | None = None
        self._chart: ft.Container | None = None
        self._title_text: ft.Text | None = None

    def main(self, page: ft.Page):
        self.page = page
        self._setup_window()
        self._setup_fonts()
        self._setup_icon()
        self._create_ui()          # 先渲染 UI
        self._show_connecting()    # 显示"正在连接"
        page.on_resized = self._on_window_resized
        page.update()
        self._connect_async()      # 后台连接

    def _setup_window(self):
        self.page.title = "TaskSense - 甘特图"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.window.frameless = False
        self.page.window.title_bar_hidden = True
        self.page.window.title_bar_buttons_hidden = True
        self.page.window.bgcolor = ft.Colors.TRANSPARENT
        self.page.window.on_close = lambda e: self._on_window_close()
        self.page.window.width = round(1200 * SCALE)
        self.page.window.height = round(750 * SCALE)
        self.page.window.min_width = round(700 * SCALE)
        self.page.window.min_height = round(450 * SCALE)
        self.page.padding = 0; self.page.spacing = 0; self.page.margin = 0
        self.page.bgcolor = ft.Colors.TRANSPARENT

    def _setup_fonts(self):
        fonts_dir = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "..", "resources"))
        self.page.fonts = {
            theme.font_family: os.path.join(fonts_dir, "HarmonyOS_Sans_SC_Medium.ttf"),
            theme.font_family_bold: os.path.join(fonts_dir, "HarmonyOS_Sans_SC_Bold.ttf"),
        }

    def _setup_icon(self):
        icon_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "..", "resources", "concept_paperplane.ico"))
        self.page.window.icon = icon_path

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
                client = SocketClient(tag="gantt")
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
        self._refresh(pull=False)
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
                mouse_cursor=ft.MouseCursor.BASIC,
                on_click=on_click,
            )

        def make_max_btn():
            if self.page and self.page.window.maximized:
                return win_btn(ft.Icons.FULLSCREEN_EXIT, self._maximize, "还原")
            return win_btn(ft.Icons.CROP_SQUARE, self._maximize, "最大化")

        self._max_btn = make_max_btn()

        drag_area = ft.WindowDragArea(ft.GestureDetector(
            content=ft.Container(expand=True), mouse_cursor=ft.MouseCursor.BASIC,
            on_double_tap=self._on_title_double_tap, on_hover=self._on_title_hover),
            expand=True)

        self._title_text = ft.Text("甘特图", size=s(12), color=theme.text_secondary, font_family=ff)

        bar_row = ft.Row([
            ft.Container(width=s(8)),
            ft.Image(src=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "resources", "concept_paperplane.ico")), width=s(18), height=s(18), fit=ft.ImageFit.CONTAIN),
            ft.Container(width=s(10)),
            ft.Icon(ft.Icons.CALENDAR_VIEW_WEEK, size=s(15), color=theme.info),
            ft.Container(width=s(6)),
            ft.Container(content=self._title_text),
            drag_area,
            win_btn(ft.Icons.REMOVE, self._minimize, "最小化"),
            self._max_btn,
            win_btn(ft.Icons.CLOSE, lambda e: self._do_close(), "关闭", hover_color=ft.Colors.RED_900),
        ], spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER)

        self._title_bar = ft.Container(content=bar_row, height=H, bgcolor=theme.surface,
            border=ft.border.only(bottom=ft.BorderSide(1, ft.Colors.with_opacity(0.10, ft.Colors.WHITE))))

        self._chart = ft.Container(expand=True, bgcolor=theme.bg,
            padding=ft.padding.all(s(16)))

        self._body = ft.Container(expand=True, bgcolor=theme.bg)

        self.page.add(ft.Container(content=ft.Column([
            self._title_bar, ft.Divider(height=1, color=theme.border), self._body,
        ], spacing=0, tight=True, expand=True), bgcolor=ft.Colors.TRANSPARENT, expand=True))

    # ── 数据刷新 ──

    def _refresh(self, pull: bool = True):
        from app.config.theme import s
        if pull and self._client:
            try:
                state_dict = self._client.get_state()
                state.load_from_dict(state_dict)
            except Exception:
                return
        ff = theme.font_family
        scheduled = [t for t in state.get_all_tasks()
                      if t.status.value in ("scheduled", "in_progress")]
        if not scheduled:
            self._body.content = ft.Container(
                ft.Text("暂无已排程/进行中任务", size=s(13), color=theme.text_secondary, font_family=ff),
                expand=True, alignment=ft.alignment.center, bgcolor=theme.bg)
            try: self._body.update()
            except: pass
            return

        # 计算时间范围
        now = datetime.now()
        starts = [t.planned_start or now for t in scheduled]
        ends = [t.planned_end or (s + timedelta(hours=max(1, t.estimated_hours or 1))) 
                for t, s in zip(scheduled, starts)]
        all_dates = starts + ends
        min_date = min(all_dates).replace(hour=0, minute=0, second=0)
        max_date = max(all_dates).replace(hour=23, minute=59, second=59)
        if max_date <= min_date:
            max_date = min_date + timedelta(days=7)
        total_days = (max_date - min_date).days + 1
        day_width = max(80, min(160, (self.page.width - s(280)) // max(total_days, 1)))

        # 表头
        header_cells = [ft.Container(width=s(240))]
        for i in range(total_days):
            d = min_date + timedelta(days=i)
            label = d.strftime("%m/%d")
            header_cells.append(ft.Container(
                ft.Text(label, size=s(12), color=theme.text_secondary, font_family=ff,
                        text_align=ft.TextAlign.CENTER),
                width=day_width))
        header_row = ft.Row(header_cells, spacing=0)

        # 任务行

        task_rows = []
        for t in sorted(scheduled, key=lambda x: (x.planned_start or datetime.max)):
            cells = [ft.Container(
                ft.Column([
                    ft.Text(t.title[:40], size=s(13), color=theme.text_primary, font_family=ff,
                            max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Text(f"{t.employee_name or ''}  {t.priority.value.upper()}", 
                            size=s(11), color=theme.text_secondary, font_family=ff,
                            max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                ], spacing=s(2), tight=True),
                width=s(240), padding=ft.padding.only(left=s(8), right=s(4)))]

            t_start = t.planned_start or now
            t_end = t.planned_end or (t_start + timedelta(hours=max(1, t.estimated_hours or 1)))
            offset_days = max(0, (t_start - min_date).days)
            bar_days = max(1, (t_end - t_start).days + 1)
            bar_color = _PRI_COLORS.get(t.priority.value, "#5294e2")

            bar_cells = [ft.Container(width=offset_days * day_width)]
            bar_cells.append(ft.Container(
                ft.Text(t.title, size=s(11), color=ft.Colors.WHITE, font_family=ff,
                        max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                width=bar_days * day_width - s(4), height=s(22),
                bgcolor=ft.Colors.with_opacity(0.75, bar_color),
                border_radius=s(4), alignment=ft.alignment.center,
                padding=ft.padding.only(left=s(6), right=s(6))))
            remaining = total_days - offset_days - bar_days
            if remaining > 0:
                bar_cells.append(ft.Container(width=remaining * day_width))

            cells.extend(bar_cells)
            task_rows.append(ft.Container(
                ft.Row(cells, spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.padding.symmetric(vertical=s(3)),
                border=ft.border.only(bottom=ft.BorderSide(1, theme.border))))

        self._title_text.value = f"甘特图  -  {len(scheduled)} 个任务"
        content = ft.Column([
            ft.Container(header_row, padding=ft.padding.only(bottom=s(6)),
                         border=ft.border.only(bottom=ft.BorderSide(1, theme.divider))),
            ft.ListView(task_rows, expand=True, spacing=0,
                        padding=ft.padding.only(top=s(4))),
        ], spacing=0, tight=True, expand=True)

        self._body.content = content
        try: self._body.update()
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
                mouse_cursor=ft.MouseCursor.BASIC,
                on_click=self._maximize)

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
