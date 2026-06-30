"""UI 应用初始化 — VS Code 风格无边框窗口 + HarmonyOS 字体."""

import os
import flet as ft

from app.config.theme import theme, SCALE


class TaskSenseApp:
    def __init__(self):
        self.page: ft.Page | None = None
        self.board_page = None
        self.title_bar: ft.Container | None = None
        self.bar_button_row: ft.Container | None = None

    def main(self, page: ft.Page):
        self.page = page
        self._setup_window()
        self._setup_fonts()
        self._create_ui()

        # ── 加载设置、检查 API ──
        from app.config.settings_manager import SettingsManager
        mgr = SettingsManager()
        mgr.load()
        api_ready = bool(mgr.get("llm", "api_key", ""))

        from app.ui.pages.board_page import BoardPage
        self.board_page = BoardPage(api_ready=api_ready)
        self.board_page.load_demo_data()

        self.main_content.content = self.board_page.build(page)
        self._setup_keyboard(page)
        page.update()

        # 启动后提示
        from app.ui.widgets.toast import Toast
        if not api_ready:
            Toast.show(page, "API Key 未配置，AI 功能不可用。请在设置中配置 LLM API Key。", "warning", 0)

    def _setup_window(self):
        self.page.title = "TaskSense — 航空维护智能看板"
        self.page.theme_mode = ft.ThemeMode.DARK

        self.page.window.frameless = False
        self.page.window.title_bar_hidden = True
        self.page.window.title_bar_buttons_hidden = True
        self.page.window.bgcolor = ft.Colors.TRANSPARENT

        self.page.window.width = round(1400 * SCALE)
        self.page.window.height = round(900 * SCALE)
        self.page.window.min_width = round(900 * SCALE)
        self.page.window.min_height = round(500 * SCALE)

        self.page.padding = 0
        self.page.spacing = 0
        self.page.margin = 0
        self.page.bgcolor = ft.Colors.TRANSPARENT

    def _setup_fonts(self):
        fonts_dir = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "..", "sources"))
        self.page.fonts = {
            theme.font_family: os.path.join(fonts_dir, "HarmonyOS_Sans_SC_Medium.ttf"),
            theme.font_family_bold: os.path.join(fonts_dir, "HarmonyOS_Sans_SC_Bold.ttf"),
        }

    # ═══════════════════════════════
    # 整体布局
    # ═══════════════════════════════

    def _create_ui(self):
        self.bar_button_row = self._create_bar_button_row()
        self.title_bar = self._create_title_bar()
        self.main_content = ft.Container(expand=True, bgcolor=theme.bg)

        self.main_container = ft.Container(
            content=ft.Column([
                self.title_bar,
                self.main_content,
                ft.Container(
                    height=round(24 * SCALE),
                    bgcolor=theme.surface,
                    border=ft.border.only(
                        top=ft.BorderSide(width=1, color=theme.border)),
                    content=ft.Row([
                        ft.Text(
                            "  Ctrl+K  命令面板  |  点击卡片查看详情  |  拖拽移动任务  |  Esc 关闭面板",
                            size=theme.font_xs, color=theme.text_disabled,
                            font_family=theme.font_family),
                    ]),
                    padding=ft.padding.only(left=theme.pad_md, top=round(4 * SCALE)),
                ),
            ], expand=True, spacing=0),
            bgcolor=ft.Colors.TRANSPARENT,
            expand=True,
        )
        self.page.add(self.main_container)

    # ═══════════════════════════════
    # 标题栏
    # ═══════════════════════════════

    def _create_title_bar(self):
        """标题栏。"""
        return ft.Container(
            content=ft.Row([
                ft.WindowDragArea(
                    ft.GestureDetector(
                        content=ft.Container(
                            content=ft.Row([
                                ft.Text("✈", size=theme.font_lg),
                                ft.Text("TaskSense", size=theme.font_sm,
                                        weight=ft.FontWeight.W_600,
                                        color=ft.Colors.WHITE,
                                        font_family=theme.font_family),
                                ft.Text("— 航空维护智能看板", size=theme.font_xs,
                                        color=ft.Colors.GREY_500,
                                        font_family=theme.font_family),
                                ft.Container(expand=True),
                            ], spacing=theme.spacing_sm),
                            expand=True, height=50,
                            padding=ft.padding.only(left=theme.pad_lg),
                            bgcolor=theme.surface,
                            on_hover=self._update_title_bar,
                        ),
                        on_double_tap=self._on_title_double_tap,
                    ),
                    expand=True,
                    on_hover=self._update_title_bar,
                ),
                self.bar_button_row,
            ], spacing=0),
            height=37,
            bgcolor=theme.surface,
            border=ft.border.only(
                bottom=ft.BorderSide(width=1, color=theme.border)),
        )

    def _create_bar_button_row(self):
        """窗口控制按钮行。"""
        return ft.Container(
            content=ft.Row([
                self._create_title_button(
                    ft.Icons.REMOVE, self._minimize_window,
                    hover_color=ft.Colors.GREY_800, tooltip="最小化"),
                self._create_maximize_button(),
                self._create_title_button(
                    ft.Icons.CLOSE, self._close_window,
                    hover_color=ft.Colors.RED_900, tooltip="关闭"),
            ], spacing=0),
        )

    def _create_maximize_button(self):
        """动态最大化/还原按钮。"""
        if self.page and self.page.window.maximized:
            icon, tip = ft.Icons.FULLSCREEN_EXIT, "还原"
        else:
            icon, tip = ft.Icons.CROP_SQUARE, "最大化"
        return self._create_title_button(
            icon, self._maximize_window, tooltip=tip)

    def _create_title_button(self, icon, on_click,
                             hover_color=ft.Colors.GREY_800, tooltip=""):
        return ft.IconButton(
            icon=icon,
            icon_size=16,
            width=45,
            height=37,
            on_click=on_click,
            icon_color=ft.Colors.WHITE,
            style=ft.ButtonStyle(
                bgcolor=ft.Colors.TRANSPARENT,
                overlay_color=hover_color,
                shape=ft.RoundedRectangleBorder(radius=0),
            ),
            mouse_cursor=ft.MouseCursor.BASIC,
            tooltip=ft.Tooltip(
                message=tooltip,
                bgcolor="#202020",
                wait_duration=1000,
                prefer_below=True,
                vertical_offset=20,
                text_style=ft.TextStyle(color=ft.Colors.WHITE),
            ),
        )

    # ═══════════════════════════════
    # 窗口操作
    # ═══════════════════════════════

    def _update_title_bar(self, e):
        self._update_maximize_button()

    def _update_maximize_button(self):
        """刷新最大化按钮图标。"""
        if self.title_bar and self.bar_button_row:
            new_row = self._create_bar_button_row()
            self.title_bar.content.controls[1] = new_row
            self.bar_button_row = new_row
            self.title_bar.update()

    def _minimize_window(self, e):
        self.page.window.minimized = True
        self.page.update()

    def _maximize_window(self, e):
        self.page.window.maximized = not self.page.window.maximized
        self.page.update()

    def _on_title_double_tap(self, e):
        """标题栏双击 — 最大化/还原。"""
        self.page.window.maximized = not self.page.window.maximized
        self.page.update()

    def _close_window(self, e):
        self.page.window.close()

    # ═══════════════════════════════
    # 键盘
    # ═══════════════════════════════

    def _setup_keyboard(self, page: ft.Page):
        def on_kb(e: ft.KeyboardEvent):
            if self.board_page:
                self.board_page.handle_keyboard(e, page)
        page.on_keyboard_event = on_kb


def run():
    ft.app(target=TaskSenseApp().main)
