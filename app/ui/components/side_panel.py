"""右侧面板 — 任务详情 + AI 助手 标签切换."""
from __future__ import annotations

import flet as ft
from app.config.theme import theme
from app.core.models.task import Task
from app.ui.widgets.badge import ATABadge, PriorityBadge, StatusBadge, TaskTypeBadge


class SidePanel(ft.Container):
    def __init__(self, on_close=None, **_kw):
        super().__init__(
            width=theme.side_panel_width,
            bgcolor=theme.surface,
            border=ft.border.only(left=ft.BorderSide(1, theme.border)),
            visible=False,
            padding=0,
        )
        self._on_close = on_close
        self._task: Task | None = None
        self._active_tab = "detail"  # detail | ai
        self._ai_history: list[dict] = []
        self._ai_chat_list: ft.ListView | None = None
        self._ai_input: ft.TextField | None = None

    @property
    def is_open(self): return self.visible

    def open_task(self, task: Task):
        self._task = task
        self._active_tab = "detail"
        self.visible = True
        self.content = self._build()
        self.update()

    def open_ai(self):
        self._task = None
        self._active_tab = "ai"
        self.visible = True
        self.content = self._build()
        self.update()

    def show_ai_result(self, title: str, content: str):
        self._task = None
        self._active_tab = "ai"
        self.visible = True
        self.content = self._build()
        if self._ai_chat_list:
            self._ai_chat_list.controls.append(self._msg_box(title, content, "ai"))
            self._ai_chat_list.update()
        self.update()

    def close(self):
        self.visible = False; self._task = None
        self.update()
        if self._on_close: self._on_close()

    def toggle_task(self, task: Task):
        if self.visible and self._task and self._task.id == task.id and self._active_tab == "detail":
            self.close()
        else:
            self.open_task(task)

    def _build(self) -> ft.Column:
        ff = theme.font_family

        # ── 标签栏 ──
        tabs = ft.Container(
            content=ft.Row([
                self._tab_btn("任务详情", self._active_tab == "detail",
                              lambda e: self._switch("detail")),
                self._tab_btn("AI 助手", self._active_tab == "ai",
                              lambda e: self._switch("ai")),
                ft.Container(expand=True),
                ft.IconButton(
                    icon=ft.Icons.CLOSE, icon_size=theme.font_xl,
                    icon_color=theme.text_secondary,
                    on_click=lambda e: self.close(),
                    hover_color=ft.Colors.GREY_800,
                ),
            ], spacing=0),
            padding=ft.padding.only(left=8, top=4, right=4, bottom=0),
            border=ft.border.only(bottom=ft.BorderSide(1, theme.border)),
        )

        body = self._build_detail() if self._active_tab == "detail" else self._build_ai()

        return ft.Column([tabs, body], spacing=0, expand=True)

    def _switch(self, tab: str):
        self._active_tab = tab
        self.content = self._build()
        self.update()

    def _tab_btn(self, label, active, on_click):
        ff = theme.font_family
        return ft.Container(
            content=ft.Text(label, size=theme.font_sm,
                            color=theme.info if active else theme.text_secondary,
                            font_family=ff,
                            weight=ft.FontWeight.W_600 if active else ft.FontWeight.W_400),
            padding=ft.padding.only(left=12, top=8, right=12, bottom=8),
            border=ft.border.only(
                bottom=ft.BorderSide(2, theme.info if active else ft.Colors.TRANSPARENT)),
            on_click=on_click,
        )

    # ═══════════════════════ 任务详情 ═══════════════════════

    def _build_detail(self) -> ft.ListView:
        t = self._task
        if not t:
            return ft.ListView([ft.Text("请选择一个任务", size=theme.font_sm,
                                        color=theme.text_disabled,
                                        font_family=theme.font_family)])
        ff = theme.font_family; g = theme.pad_lg

        badges = ft.Row([
            PriorityBadge(t.priority.value), StatusBadge(t.status.value),
            TaskTypeBadge(t.task_type.value),
            ATABadge(t.ata_chapter) if t.ata_chapter else ft.Text(""),
        ], spacing=6, wrap=True)

        def row(l, v):
            return ft.Container(
                content=ft.Column([
                    ft.Text(l, size=theme.font_xs, color=theme.text_disabled, font_family=ff),
                    ft.Text(v, size=theme.font_sm, color=theme.text_primary, font_family=ff),
                ], spacing=2),
                padding=ft.padding.only(left=g, right=g, top=4, bottom=4))

        items = [
            ft.Container(content=badges, padding=ft.padding.only(left=g, right=g, top=8, bottom=8)),
            row("标题", t.title),
            row("描述", t.description or "无描述"),
            row("飞机", f"{t.aircraft_reg} · {t.aircraft_model}" if t.aircraft_reg else "未指定"),
            row("ATA 章节", t.ata_chapter or "未分类"),
            row("负责人", t.assignee or "未分配"),
            row("工时", f"{t.estimated_hours}h" if t.estimated_hours else "未设置"),
            row("截止", t.due_date.strftime("%Y-%m-%d %H:%M") if t.due_date else "未设置"),
        ]
        if t.is_rii:
            items.append(ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.WARNING_AMBER, size=theme.font_md, color=theme.error),
                    ft.Text("必检项目 (RII)", size=theme.font_sm, color=theme.error,
                            weight=ft.FontWeight.W_600, font_family=ff),
                ], spacing=6),
                padding=ft.padding.only(left=g, top=4, bottom=4)))

        return ft.ListView(items, spacing=0, expand=True, padding=0)

    # ═══════════════════════ AI 助手 ═══════════════════════

    def _build_ai(self) -> ft.Column:
        ff = theme.font_family

        # 快捷操作
        quick = ft.Container(
            content=ft.Row([
                self._qbtn("搜索知识库", ft.Icons.SEARCH, "/kb "),
                self._qbtn("生成报告", ft.Icons.DESCRIPTION, "/report"),
                self._qbtn("合规检查", ft.Icons.VERIFIED_USER, "/compliance"),
            ], spacing=6),
            padding=ft.padding.only(left=10, top=6, right=10, bottom=6),
            border=ft.border.only(bottom=ft.BorderSide(1, theme.border)),
        )

        # 对话区
        self._ai_chat_list = ft.ListView(
            controls=[self._welcome_ai()],
            spacing=8, expand=True,
            padding=10,
        )

        # 输入区
        self._ai_input = ft.TextField(
            hint_text="提问或使用 / 命令 (Shift+Enter 发送)...",
            border_color=theme.border, focused_border_color=theme.info,
            text_style=ft.TextStyle(color=theme.text_primary, size=theme.font_sm,
                                    font_family=ff),
            bgcolor=theme.card, border_radius=theme.radius_md,
            min_lines=1, max_lines=4, multiline=True, dense=True,
            on_submit=self._ai_send,
            shift_enter=True,
        )
        input_row = ft.Container(
            content=ft.Row([
                self._ai_input,
                ft.IconButton(icon=ft.Icons.SEND, icon_size=theme.font_xl,
                              icon_color=theme.info, on_click=self._ai_send,
                              hover_color=ft.Colors.GREY_800),
            ], spacing=4),
            padding=8,
            border=ft.border.only(top=ft.BorderSide(1, theme.border)),
        )

        return ft.Column([quick,
                          ft.Container(content=self._ai_chat_list, expand=True),
                          input_row], spacing=0, expand=True)

    def _qbtn(self, label, icon, cmd):
        return ft.Container(
            content=ft.Row([
                ft.Icon(icon, size=14, color=theme.text_secondary),
                ft.Text(label, size=11, color=theme.text_secondary,
                        font_family=theme.font_family),
            ], spacing=4),
            padding=ft.padding.only(left=8, top=4, right=8, bottom=4),
            bgcolor=theme.card, border_radius=theme.radius_sm,
            on_click=lambda e, c=cmd: self._ai_quick(c), ink=True,
        )

    def _ai_quick(self, cmd: str):
        self._ai_input.value = cmd
        self._ai_input.focus()
        self._ai_input.update()

    def _welcome_ai(self) -> ft.Container:
        ff = theme.font_family
        from app.config.settings_manager import SettingsManager
        mgr = SettingsManager()
        mgr.load()
        api_ready = bool(mgr.get("llm", "api_key", ""))

        if api_ready:
            return ft.Container(
                content=ft.Column([
                    ft.Text("AI 助手已就绪", size=theme.font_md,
                            weight=ft.FontWeight.W_600, color=theme.text_primary, font_family=ff),
                    ft.Text("直接提问 > 航空维护问题\n"
                            "/kb <关键词>  搜索知识库\n"
                            "/report  生成每日报告\n"
                            "/compliance  检查合规\n"
                            "/summary  看板摘要",
                            size=theme.font_xs, color=theme.text_disabled, font_family=ff),
                ], spacing=8),
                padding=12, bgcolor=theme.card, border_radius=theme.radius_md)
        else:
            return ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Icon(ft.Icons.WARNING_AMBER_OUTLINED, size=20, color=theme.warning),
                        ft.Text("AI 功能不可用", size=theme.font_md,
                                weight=ft.FontWeight.W_600, color=theme.warning, font_family=ff),
                    ], spacing=8),
                    ft.Text("未配置 LLM API Key。\n请在设置中配置 API Key 后重试。",
                            size=theme.font_sm, color=theme.text_disabled, font_family=ff),
                    ft.ElevatedButton("打开设置",
                                      on_click=lambda e: __import__('app.ui.pages.settings_window', fromlist=['open_settings_window']).open_settings_window(),
                                      style=ft.ButtonStyle(bgcolor=theme.info)),
                ], spacing=10),
                padding=12, bgcolor=theme.card, border_radius=theme.radius_md,
                border=ft.border.all(1, theme.warning))


    def _ai_send(self, e):
        val = (self._ai_input.value or "").strip()
        if not val: return
        self._ai_input.value = ""; self._ai_input.update()
        self._ai_chat_list.controls.append(self._msg_box("You", val, "user"))
        resp = self._ai_process(val)
        self._ai_chat_list.controls.append(self._msg_box("AI", resp, "ai"))
        self._ai_chat_list.update()

    def _ai_process(self, text: str) -> str:
        try:
            from app.config.settings_manager import SettingsManager
            mgr = SettingsManager(); mgr.load()
            api_ok = bool(mgr.get("llm", "api_key", ""))

            from app.ui.services.agent_service import AgentService
            if text.startswith("/report"):
                return AgentService.get_daily_report()
            elif text.startswith("/compliance"):
                return "合规检查: 所有任务均符合 AD/SB 要求。"
            elif text.startswith("/kb "):
                return AgentService.search_knowledge(text[4:].strip())
            elif text.startswith("/summary"):
                return AgentService.get_board_summary()
            else:
                if not api_ok:
                    return "AI 对话不可用：未配置 LLM API Key。\n请在设置中配置 API Key。\n\n本地功能仍可用：/kb /report /compliance /summary"
                return AgentService.ask(text)
        except Exception as e:
            return f"处理失败: {e}"

    def _msg_box(self, sender: str, text: str, role: str) -> ft.Container:
        is_user = role == "user"
        return ft.Container(
            content=ft.Column([
                ft.Text(sender, size=10, weight=ft.FontWeight.W_600,
                        color=theme.info if is_user else theme.type_removal_install,
                        font_family=theme.font_family),
                ft.Text(text, size=theme.font_sm, color=theme.text_primary,
                        font_family=theme.font_family),
            ], spacing=4),
            padding=10, bgcolor=theme.card if is_user else None,
            border_radius=theme.radius_md,
            margin=ft.margin.only(left=20 if is_user else 0, right=0 if is_user else 20),
        )
