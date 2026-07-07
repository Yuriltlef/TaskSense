"""UI 应用初始化 — VS Code 风格无边框窗口 + HarmonyOS 字体."""

import os
from datetime import datetime
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

        # ── 加载持久化状态（若存在）──
        from app.core.services.persistence_service import persistence_service
        from app.core.services.employee_service import employee_service
        from app.core.services.log_service import log_service
        from app.ui.pages.board_page import BoardPage

        employee_service.load()
        persistence_service.set_path("data/board_state.json")
        from app.core.logging import log
        log.section("TaskSense 启动")
        log.info("boot", f"employees={employee_service.employee_count()}")
        log_dir = "data/logs"
        os.makedirs(log_dir, exist_ok=True)
        log_service.set_path(
            f"{log_dir}/log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        loaded = persistence_service.load()
        log.info("boot", f"persistence loaded={loaded}")

        self.board_page = BoardPage(api_ready=api_ready)
        if not loaded:
            log.error("boot", "board_state.json not found")
        else:
            from app.core.state import state
            if len(state.get_all_tasks()) == 0:
                log.warn("boot", "board_state.json is empty")
        persistence_service.start_auto_save(debounce_seconds=5.0)

        # ── 启动自动流转调度器 ──
        from app.core.services.board_scheduler import board_scheduler
        board_scheduler.start(interval=10.0)

        # ── 启动外部变更轮询（员工窗口修改后的自动刷新）──
        self._start_sync_polling()

        self.main_content.content = self.board_page.build(page)
        self._build_unified_title_bar()
        self._setup_keyboard(page)
        page.on_resized = self._on_window_resized
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
        self.page.window.on_close = lambda e: self._on_window_close()

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
                    overlay_color=theme.border_active,
                    shape=ft.RoundedRectangleBorder(radius=0),
                ),
                tooltip=ft.Tooltip(message=tooltip, bgcolor=theme.tooltip_bg,
                                   text_style=_tt_style,
                                   wait_duration=1500),
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
                tooltip=ft.Tooltip(message=tooltip, bgcolor=theme.tooltip_bg,
                                   text_style=_tt_style,
                                   wait_duration=1500),
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
        clear_btn = ft.IconButton(
            icon=ft.Icons.CLOSE, icon_size=s(12),
            icon_color=theme.text_secondary,
            width=s(22), height=s(22),
            visible=False,
            style=ft.ButtonStyle(
                bgcolor=ft.Colors.TRANSPARENT,
                shape=ft.RoundedRectangleBorder(radius=s(4)),
            ),
            on_click=bp._on_search_clear,
        )
        bp._search_clear_btn = clear_btn
        search_box = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.SEARCH, size=s(14), color=theme.accent),
                sf,
                clear_btn,
            ], spacing=s(6)),
            width=max(320, self.page.width // 3),
            height=s(28),
            bgcolor=theme.card_hover,
            border=ft.border.all(1, theme.border_active),
            border_radius=s(6),
            padding=ft.padding.symmetric(horizontal=s(10)),
            alignment=ft.alignment.center_left,
            animate=ft.Animation(200, ft.AnimationCurve.EASE_OUT),
        )
        bp._search_box = search_box

        # ── 窗口按钮（在 WindowDragArea 外部）──
        window_btns = [
            win_btn(ft.Icons.REMOVE, self._minimize_window, "最小化"),
            *self._window_ctrls,
            win_btn(ft.Icons.CLOSE, self._close_window, "关闭", hover_color=ft.Colors.RED_900),
        ]

        # ── 拖拽 spacer：GestureDetector 只包裹空 Container ──
        def _drag_spacer():
            return ft.WindowDragArea(
                ft.GestureDetector(
                    content=ft.Container(expand=True),
                    mouse_cursor=ft.MouseCursor.BASIC,
                    on_double_tap=self._on_title_double_tap,
                    on_hover=self._on_title_hover,
                ),
                expand=True,
            )

        # ── 左侧功能区 ──
        left_group = ft.Row([
            ft.Container(width=s(8)),
            ft.Container(content=ft.Text("✈", size=s(15), font_family=ff),
                         padding=ft.padding.only(left=s(2), right=s(6)),
                         height=H, alignment=ft.alignment.center),
            ft.Container(width=s(6)),
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.ADD, size=icon_sz, color=ft.Colors.WHITE),
                    ft.Text("新建任务", size=s(12), font_family=ff, color=ft.Colors.WHITE),
                ], spacing=s(2)),
                blur=(10, 10),
                bgcolor=ft.Colors.with_opacity(0.18, theme.accent),
                border=ft.border.all(1, ft.Colors.with_opacity(0.35, theme.accent)),
                border_radius=s(6),
                padding=ft.padding.only(left=s(12), top=s(3), right=s(12), bottom=s(3)),
                height=s(26),
                ink=True,
                animate=ft.Animation(150, ft.AnimationCurve.EASE_OUT),
                on_click=bp._on_create_task,
            ),
            ft.Container(width=s(6)),
            icon_btn(ft.Icons.REFRESH, lambda e: bp._refresh_board(), "刷新看板"),
            ft.Container(width=s(4)),
            icon_btn(ft.Icons.FILTER_LIST, bp._on_filter_click, "筛选任务"),
            ft.Container(width=s(4)),
            self._build_ai_menu_button(bp),
        ], spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER)

        # ── 右侧功能区 ──
        right_group = ft.Row([
            icon_btn(ft.Icons.PSYCHOLOGY_OUTLINED, lambda e: bp._open_ai_panel(),
                     "AI 助手", icon_color=theme.ai_icon),
            icon_btn(ft.Icons.SETTINGS_OUTLINED, bp._on_settings_click, "设置"),
            icon_btn(ft.Icons.PERSON_OUTLINE, lambda e: bp._open_employee_page(), "员工工作台"),
        ], spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER)

        # ── 最终标题栏：左组 | 拖拽区 | 搜索框 | 拖拽区 | 右组 | 窗口按钮 ──
        bar_row = ft.Row(
            [left_group, _drag_spacer(), search_box, _drag_spacer(), right_group] + window_btns,
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

    def _on_window_resized(self, e):
        bp = self.board_page
        if bp._search_box and self.page:
            bp._search_box.width = max(320, self.page.width // 3)
            bp._search_box.update()

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
            tooltip=ft.Tooltip(message=tooltip, bgcolor=theme.tooltip_bg,
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
        """自定义标题栏关闭按钮：清理员工进程后关闭窗口。"""
        from app.ui.pages.board_page import kill_employee_processes
        kill_employee_processes()
        self.page.window.close()

    def _on_window_close(self):
        """系统关闭按钮回调：清理员工进程。"""
        from app.ui.pages.board_page import kill_employee_processes
        kill_employee_processes()

    # ═══════════════════════════════
    # 外部变更轮询
    # ═══════════════════════════════

    def _start_sync_polling(self):
        """后台线程：处理员工窗口命令 + 检测外部状态变更。"""
        import threading, time

        self._polling_active = True

        def poll():
            while self._polling_active:
                time.sleep(0.5)
                if not self._polling_active:
                    return
                try:
                    # 1. 处理员工窗口发来的命令队列
                    from app.core.services.command_queue import process_pending_commands
                    processed = process_pending_commands()
                    if processed > 0:
                        # 命令处理后保存状态
                        from app.core.services.persistence_service import persistence_service
                        persistence_service.save()
                        if self.board_page:
                            self.board_page._refresh_board()

                    # 2. 检测外部直接修改（兼容旧逻辑）
                    from app.core.services.persistence_service import persistence_service
                    if persistence_service.reload_if_changed():
                        if self.board_page and self.page:
                            self.board_page._refresh_board()
                except Exception:
                    pass

        t = threading.Thread(target=poll, daemon=True)
        t.start()

    # ═══════════════════════════════
    # 键盘
    # ═══════════════════════════════

    # ═══════════════════════════════
    # AI 工具菜单 (overlay 定位)
    # ═══════════════════════════════

    def _build_ai_menu_button(self, bp):
        """AI 工具菜单按钮 + overlay 下拉。"""
        H = s(34); btn_w = s(36)
        btn = ft.IconButton(
            icon=ft.Icons.MENU, icon_size=s(16), icon_color=ft.Colors.GREY_400,
            width=btn_w, height=H,
            style=ft.ButtonStyle(
                bgcolor=ft.Colors.TRANSPARENT,
                overlay_color=theme.border_active,
                shape=ft.RoundedRectangleBorder(radius=0),
            ),
            tooltip=ft.Tooltip(message="AI 工具", bgcolor=theme.tooltip_bg,
                               text_style=ft.TextStyle(color=ft.Colors.WHITE,
                                                       font_family=theme.font_family),
                               wait_duration=1500),
            on_click=lambda e: self._show_ai_menu(bp, e),
        )
        self._ai_menu_btn = btn
        return btn

    def _show_ai_menu(self, bp, e):
        # 关闭已有菜单避免重叠
        self._close_ai_menu(bp, None)

        # 高亮按钮
        if hasattr(self, '_ai_menu_btn') and self._ai_menu_btn:
            self._ai_menu_btn.style.bgcolor = "#22ffffff"
            try: self._ai_menu_btn.update()
            except Exception: pass

        ff = theme.font_family
        cmds = [
            ("生成大纲", ft.Icons.ARTICLE_OUTLINED, "outline"),
            ("生成任务", ft.Icons.PLAYLIST_ADD_OUTLINED, "gen_tasks"),
            ("自动分类", ft.Icons.LABEL_OUTLINED, "classify"),
            ("自动排程", ft.Icons.SCHEDULE_OUTLINED, "schedule"),
            ("自动验收", ft.Icons.VERIFIED_OUTLINED, "acceptance"),
            ("生成报表", ft.Icons.ASSESSMENT_OUTLINED, "report"),
            ("任务审核", ft.Icons.FACT_CHECK_OUTLINED, "review"),
        ]
        items = []
        for label, icon, cmd in cmds:
            items.append(ft.TextButton(
                content=ft.Row([
                    ft.Icon(icon, size=s(14), color=theme.info),
                    ft.Text(label, size=s(12), color=theme.text_primary, font_family=ff),
                ], spacing=s(8)),
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.TRANSPARENT,
                    overlay_color="#22ffffff",
                    shape=ft.RoundedRectangleBorder(radius=s(4)),
                    padding=ft.padding.symmetric(horizontal=s(10), vertical=s(4)),
                ),
                on_click=lambda _, c=cmd: self._close_ai_menu(bp, c),
            ))

        menu_left = s(230)
        TB_H = s(34)
        menu = ft.Container(
            content=ft.Column(items, spacing=s(2), tight=True),
            bgcolor=theme.surface,
            border=ft.border.all(1, theme.border),
            border_radius=s(8),
            padding=ft.padding.all(s(6)),
            shadow=ft.BoxShadow(spread_radius=1, blur_radius=16, color=theme.dialog_shadow),
            left=menu_left, top=TB_H,
            width=180,
        )

        dimmer = ft.Container(
            ft.GestureDetector(
                content=ft.Container(expand=True),
                on_tap=lambda _: self._close_ai_menu(bp, None),
            ),
            width=self.page.width, height=self.page.height,
        )
        overlay = ft.Stack([dimmer, menu], width=self.page.width, height=self.page.height)
        self.page.overlay.append(overlay)
        self._ai_menu_overlay = overlay
        self.page.update()

    def _close_ai_menu(self, bp, cmd):
        # 取消按钮高亮
        if hasattr(self, '_ai_menu_btn') and self._ai_menu_btn:
            self._ai_menu_btn.style.bgcolor = ft.Colors.TRANSPARENT
            try: self._ai_menu_btn.update()
            except Exception: pass

        overlay_ref = getattr(self, '_ai_menu_overlay', None)
        if overlay_ref is not None:
            self._ai_menu_overlay = None
            try:
                self.page.overlay.remove(overlay_ref)
                self.page.update()
            except Exception:
                pass
        if cmd:
            bp._run_agent_command(cmd)

    def _setup_keyboard(self, page: ft.Page):
        def on_kb(e: ft.KeyboardEvent):
            if self.board_page:
                self.board_page.handle_keyboard(e, page)
        page.on_keyboard_event = on_kb


def run():
    ft.app(target=TaskSenseApp().main)
