"""UI 应用初始化 — VS Code 风格无边框窗口 + HarmonyOS 字体."""

import os
import flet as ft

from app.config.theme import theme, SCALE, s


class TaskSenseApp:
    def __init__(self):
        self.page: ft.Page | None = None
        self.board_page = None
        self.title_bar: ft.Container | None = None
        self._last_maximized: bool | None = None  # 避免重复重建按钮
        self.bar_button_row: ft.Row | None = None

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
        self._build_unified_title_bar()
        self._setup_keyboard(page)
        page.update()

        # 启动后提示
        from app.ui.widgets.toast import Toast
        if not api_ready:
            Toast.show(page, "API Key 未配置，AI 功能不可用。请在设置中配置 LLM API Key。", "warning", 0)

    def _setup_window(self):
        self.page.title = "TaskSense"
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
        self.main_content = ft.Container(expand=True, bgcolor=theme.bg)

        self.main_container = ft.Container(
            content=ft.Column([
                self.main_content,
                ft.Container(
                    height=s(20),
                    bgcolor=theme.surface,
                    border=ft.border.only(
                        top=ft.BorderSide(width=1, color=theme.border)),
                    content=ft.Row([
                        ft.Text(
                            "  Ctrl+K 命令面板 | 点击卡片查看详情 | 拖拽移动任务 | Esc 关闭面板",
                            size=s(10), color=theme.text_disabled,
                            font_family=theme.font_family),
                    ]),
                    padding=ft.padding.only(left=theme.pad_md, top=s(2)),
                ),
            ], expand=True, spacing=0),
            bgcolor=ft.Colors.TRANSPARENT,
            expand=True,
        )
        self.page.add(self.main_container)

    # ═══════════════════════════════
    # 统一标题栏 — 所有控件合并到一条
    # ═══════════════════════════════

    def _build_unified_title_bar(self):
        """合并标题栏：✈ | 新建 | 刷新 | 过滤 | 搜索 | AI | 设置 | 用户 | 缩小 | 全屏 | 关闭"""
        bp = self.board_page
        ff = theme.font_family
        H = s(34)          # 统一高度
        icon_sz = s(16)    # 统一图标大小
        btn_w = s(36)      # 图标按钮宽度

        # ── 工具按钮工厂 ──
        _tt_style = ft.TextStyle(color=ft.Colors.WHITE, font_family=theme.font_family)

        def icon_btn(icon, on_click, tooltip, icon_color=ft.Colors.GREY_400):
            return ft.IconButton(
                icon=icon, icon_size=icon_sz, icon_color=icon_color,
                width=btn_w, height=H,
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.TRANSPARENT,
                    overlay_color="#2a2a2a",
                    shape=ft.RoundedRectangleBorder(radius=0),
                ),
                tooltip=ft.Tooltip(message=tooltip, bgcolor="#202020",
                                   text_style=_tt_style),
                on_click=on_click,
            )

        # ── 窗口按钮工厂 ──
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
                tooltip=ft.Tooltip(message=tooltip, bgcolor="#202020",
                                   text_style=_tt_style),
                on_click=on_click,
            )

        # ── 最大化按钮（动态图标）──
        def max_btn():
            if self.page and self.page.window.maximized:
                return win_btn(ft.Icons.FULLSCREEN_EXIT, self._maximize_window, "还原")
            return win_btn(ft.Icons.CROP_SQUARE, self._maximize_window, "最大化")

        self._window_ctrls = [max_btn()]

        # ── 搜索区域 ──
        sf = bp._search_field
        search_box = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.SEARCH, size=s(14), color=theme.text_disabled),
                sf,
            ], spacing=s(3)),
        )

        # ── 窗口按钮（在 WindowDragArea 外部）──
        window_btns = [
            win_btn(ft.Icons.REMOVE, self._minimize_window, "最小化"),
            *self._window_ctrls,
            win_btn(ft.Icons.CLOSE, self._close_window, "关闭", hover_color=ft.Colors.RED_900),
        ]

        # ── 内容区 ──
        content_row = ft.Row([
            ft.Container(width=s(8)),
            ft.Container(content=ft.Text("✈", size=s(15), font_family=ff),
                         padding=ft.padding.only(left=s(2), right=s(6)),
                         height=H, alignment=ft.alignment.center),
            ft.Container(width=s(6)),
            ft.ElevatedButton(
                content=ft.Row([
                    ft.Icon(ft.Icons.ADD, size=icon_sz),
                    ft.Text("新建任务", size=s(12), font_family=ff, color=ft.Colors.WHITE),
                ], spacing=s(2)),
                style=ft.ButtonStyle(
                    bgcolor="#1565c0",
                    color=ft.Colors.WHITE,
                    overlay_color="#1e88e5",
                    elevation=1,
                    padding=ft.padding.only(left=s(12), top=s(2), right=s(12), bottom=s(2)),
                    shape=ft.RoundedRectangleBorder(radius=s(4)),
                ),
                height=s(24), on_click=bp._on_create_task,
            ),
            ft.Container(width=s(6)),
            icon_btn(ft.Icons.REFRESH, lambda e: bp._refresh_board(), "刷新看板"),
            ft.Container(width=s(4)),
            icon_btn(ft.Icons.FILTER_LIST, bp._on_filter_click, "筛选任务"),
            ft.Container(expand=True),
            search_box,
            ft.Container(expand=True),
            icon_btn(ft.Icons.PSYCHOLOGY_OUTLINED, lambda e: bp._open_ai_panel(),
                     "AI 助手", icon_color="#c498e8"),
            icon_btn(ft.Icons.SETTINGS_OUTLINED, bp._on_settings_click, "设置"),
            icon_btn(ft.Icons.PERSON_OUTLINE, lambda e: None, "用户账号"),
        ], spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER)

        # WindowDragArea 包裹 GestureDetector：拖拽优先，双击作为附加手势
        # GestureDetector 必须在 WindowDragArea 内部（不能反过来），否则按钮点击失效
        drag_area = ft.WindowDragArea(
            ft.GestureDetector(
                content=ft.Container(content=content_row, expand=True),
                mouse_cursor=ft.MouseCursor.BASIC,
                on_double_tap=self._on_title_double_tap,
                on_hover=self._on_title_hover,
            ),
            expand=True,
        )

        # ── 最终标题栏 ──
        bar_row = ft.Row(
            [drag_area] + window_btns,
            spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        self.title_bar = ft.Container(
            content=bar_row,
            height=H,
            bgcolor=theme.surface,
            border=ft.border.only(
                bottom=ft.BorderSide(1, ft.Colors.with_opacity(0.10, ft.Colors.WHITE))),
        )

        # 插入到 main_container 顶部
        self.main_container.content.controls.insert(0, self.title_bar)

    # ═══════════════════════════════
    # 窗口操作
    # ═══════════════════════════════

    def _on_title_hover(self, e):
        """标题栏悬停时检测最大化状态变化（Win+↑ / 拖拽顶部等外部操作）。"""
        current = self.page.window.maximized
        if current != self._last_maximized:
            self._last_maximized = current
            self._update_maximize_button()

    def _update_maximize_button(self):
        """重建窗口按钮行以刷新最大化/还原图标。"""
        if not self.title_bar:
            return
        self._last_maximized = self.page.window.maximized
        # bar_row 是 title_bar.content，controls[-3:] 是窗口按钮
        bar_row = self.title_bar.content
        new_ctrls = list(bar_row.controls)
        # 重建窗口按钮段（最后 3 个：最小化、最大化、关闭）
        max_idx = len(new_ctrls) - 2
        if self.page.window.maximized:
            new_ctrls[max_idx] = self._win_btn(
                ft.Icons.FULLSCREEN_EXIT, self._maximize_window, "还原")
        else:
            new_ctrls[max_idx] = self._win_btn(
                ft.Icons.CROP_SQUARE, self._maximize_window, "最大化")
        bar_row.controls = new_ctrls
        self.title_bar.update()

    def _win_btn(self, icon, on_click, tooltip, hover_color=ft.Colors.GREY_800):
        H = s(34); icon_sz = s(16); btn_w = s(36)
        return ft.IconButton(
            icon=icon, icon_size=icon_sz, icon_color=ft.Colors.WHITE,
            width=btn_w, height=H,
            style=ft.ButtonStyle(
                bgcolor=ft.Colors.TRANSPARENT,
                overlay_color=hover_color,
                shape=ft.RoundedRectangleBorder(radius=0),
            ),
            mouse_cursor=ft.MouseCursor.BASIC,
            tooltip=ft.Tooltip(message=tooltip, bgcolor="#202020",
                               text_style=ft.TextStyle(color=ft.Colors.WHITE)),
            on_click=on_click,
        )

    def _minimize_window(self, e):
        self.page.window.minimized = True
        self.page.update()

    def _maximize_window(self, e):
        self.page.window.maximized = not self.page.window.maximized
        self.page.update()
        self._update_maximize_button()

    def _on_title_double_tap(self, e):
        self.page.window.maximized = not self.page.window.maximized
        self.page.update()
        self._update_maximize_button()

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
