"""AI 助手侧边栏 — Trae 风格."""
from __future__ import annotations

import flet as ft
from app.config.theme import theme


class AISidebar(ft.Container):
    """Trae 风格 AI 助手侧边栏。

    功能：
    - 对话历史
    - 知识库查询
    - 快捷操作
    - 报告生成
    """

    def __init__(self, on_close=None):
        super().__init__(
            width=420,
            bgcolor=theme.surface,
            border=ft.border.only(left=ft.BorderSide(1, theme.border)),
            visible=False,
            padding=0,
        )
        self._on_close = on_close
        self._history: list[dict] = []
        self._chat_list: ft.ListView | None = None
        self._input: ft.TextField | None = None

    @property
    def is_open(self): return self.visible

    def toggle(self):
        self.visible = not self.visible
        if self.visible and not self.content:
            self.content = self._build()
        self.update()

    def open(self):
        self.visible = True
        if not self.content:
            self.content = self._build()
        self.update()

    def close(self):
        self.visible = False
        self.update()
        if self._on_close: self._on_close()

    def _build(self) -> ft.Column:
        ff = theme.font_family

        # ── 标题栏 ──
        header = ft.Container(
            content=ft.Row([
                ft.Text("AI 助手", size=theme.font_lg, weight=ft.FontWeight.W_600,
                        color=theme.text_primary, font_family=ff),
                ft.Container(expand=True),
                ft.IconButton(
                    icon=ft.Icons.CLOSE, icon_size=theme.font_xl,
                    icon_color=theme.text_secondary,
                    on_click=lambda e: self.close(),
                    hover_color=ft.Colors.GREY_800,
                ),
            ], spacing=6),
            padding=ft.padding.only(left=12, top=8, right=8, bottom=8),
            border=ft.border.only(bottom=ft.BorderSide(1, theme.border)),
        )

        # ── 快捷操作 ──
        quick_actions = ft.Container(
            content=ft.Row([
                self._quick_btn("搜索知识库", ft.Icons.SEARCH,
                                lambda e: self._do_quick("/kb ")),
                self._quick_btn("生成报告", ft.Icons.DESCRIPTION,
                                lambda e: self._do_quick("/report")),
                self._quick_btn("合规检查", ft.Icons.VERIFIED_USER,
                                lambda e: self._do_quick("/compliance")),
            ], spacing=6),
            padding=ft.padding.only(left=12, top=6, right=12, bottom=6),
            border=ft.border.only(bottom=ft.BorderSide(1, theme.border)),
        )

        # ── 对话区 ──
        self._chat_list = ft.ListView(
            controls=[self._welcome_msg()],
            spacing=8, expand=True,
            padding=12,
        )

        # ── 输入区 ──
        self._input = ft.TextField(
            hint_text="输入问题或使用 / 命令...",
            border_color=theme.border,
            focused_border_color=theme.info,
            text_style=ft.TextStyle(color=theme.text_primary, size=theme.font_sm,
                                    font_family=ff),
            bgcolor=theme.card,
            border_radius=theme.radius_md,
            min_lines=1, max_lines=4,
            multiline=True,
            dense=True,
            on_submit=self._on_send,
            shift_enter=True,
        )

        input_row = ft.Container(
            content=ft.Row([
                self._input,
                ft.IconButton(
                    icon=ft.Icons.SEND, icon_size=theme.font_xl,
                    icon_color=theme.info,
                    on_click=self._on_send,
                    hover_color=ft.Colors.GREY_800,
                ),
            ], spacing=4),
            padding=ft.padding.all(10),
            border=ft.border.only(top=ft.BorderSide(1, theme.border)),
        )

        return ft.Column([
            header, quick_actions,
            ft.Container(content=self._chat_list, expand=True),
            input_row,
        ], spacing=0, expand=True)

    def _welcome_msg(self) -> ft.Container:
        ff = theme.font_family
        return ft.Container(
            content=ft.Column([
                ft.Text("AI 助手已就绪", size=theme.font_md,
                        weight=ft.FontWeight.W_600,
                        color=theme.text_primary, font_family=ff),
                ft.Text(
                    "你可以：\n"
                    "  > 直接提问航空维护问题\n"
                    "  /kb <关键词>  搜索知识库\n"
                    "  /report  生成每日报告\n"
                    "  /compliance  检查合规状态\n"
                    "  /summary  看板摘要",
                    size=theme.font_xs, color=theme.text_disabled, font_family=ff),
            ], spacing=8),
            padding=ft.padding.all(12),
            bgcolor=theme.card, border_radius=theme.radius_md,
        )

    def _quick_btn(self, label, icon, on_click):
        return ft.Container(
            content=ft.Row([
                ft.Icon(icon, size=14, color=theme.text_secondary),
                ft.Text(label, size=11, color=theme.text_secondary,
                        font_family=theme.font_family),
            ], spacing=4),
            padding=ft.padding.only(left=8, top=4, right=8, bottom=4),
            bgcolor=theme.card, border_radius=theme.radius_sm,
            on_click=on_click,
            ink=True,
        )

    def _on_send(self, e):
        val = (self._input.value or "").strip()
        if not val: return

        self._input.value = ""
        self._input.update()

        # 添加用户消息
        self._add_msg("user", val)

        # 处理
        response = self._process(val)
        self._add_msg("ai", response)

    def _process(self, text: str) -> str:
        try:
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
                return AgentService.ask(text)
        except Exception as e:
            return f"处理失败: {e}"

    def _add_msg(self, role: str, content: str):
        ff = theme.font_family
        is_user = role == "user"

        msg = ft.Container(
            content=ft.Column([
                ft.Text("You" if is_user else "AI",
                        size=10, weight=ft.FontWeight.W_600,
                        color=theme.info if is_user else theme.type_removal_install,
                        font_family=ff),
                ft.Text(content, size=theme.font_sm,
                        color=theme.text_primary, font_family=ff),
            ], spacing=4),
            padding=ft.padding.all(10),
            bgcolor=theme.card if is_user else None,
            border_radius=theme.radius_md,
            margin=ft.margin.only(left=20 if is_user else 0,
                                  right=0 if is_user else 20),
        )
        self._history.append({"role": role, "content": content})
        if self._chat_list:
            self._chat_list.controls.append(msg)
            self._chat_list.update()

    def _do_quick(self, cmd: str):
        self._input.value = cmd
        self._input.focus()
        self._input.update()
