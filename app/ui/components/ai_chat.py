"""AI 对话面板 — chat_bubble + ChatInput 组合。"""
from __future__ import annotations

from datetime import datetime
import flet as ft
from app.config.theme import theme
from app.ui.components.chat_bubble import user_bubble, ai_bubble, error_bubble, timestamp_label
from app.ui.components.chat_input import ChatInput


class AIChatPanel(ft.Container):
    MIN_W, MAX_W = 380, 800

    def __init__(self, width=520, on_close=None):
        super().__init__(
            width=width, bgcolor=theme.surface,
            border=ft.border.only(left=ft.BorderSide(1, theme.border)),
            visible=False, padding=0,
        )
        self._on_close = on_close
        self._chat: ft.ListView | None = None
        self._input: ChatInput | None = None
        self._busy = False
        self._msg_pairs: list[tuple[str, str, str]] = []  # (user, ai, timestamp)

    @property
    def is_open(self): return self.visible

    def toggle(self):
        if self.visible: self.close()
        else: self.open()

    def open(self):
        self.visible = True
        if not self.content: self.content = self._build()
        self.update()

    def close(self):
        self.visible = False; self.update()
        if self._on_close: self._on_close()

    def resize(self, delta: float):
        new_w = max(self.MIN_W, min(self.MAX_W, self.width - delta))
        if new_w != self.width:
            self.width = new_w
            self._rebuild_bubbles()
            self.update()

    # ═══════════════════════════════════════════════
    # Build
    # ═══════════════════════════════════════════════

    def _build(self):
        ff = theme.font_family

        hdr = ft.Container(
            ft.Row([
                ft.Text("AI 助手", size=13, weight=ft.FontWeight.W_600,
                        color=theme.text_primary, font_family=ff),
                ft.Container(expand=True),
                ft.IconButton(ft.Icons.CLOSE, icon_size=16, icon_color=theme.text_secondary,
                              on_click=lambda e: self.close()),
            ], spacing=8),
            padding=ft.padding.only(left=14, top=6, right=4, bottom=6),
            border=ft.border.only(bottom=ft.BorderSide(1, theme.border)))

        self._chat = ft.ListView(
            [self._welcome()],
            spacing=10, expand=True,
            padding=ft.padding.only(left=12, top=10, right=12, bottom=10),
        )

        self._input = ChatInput(on_send=self._handle_send)

        inp = ft.Container(
            ft.Column([
                self._input,
                ft.Row([
                    self._chip("搜索知识库", ft.Icons.SEARCH, "/kb "),
                    self._chip("生成报告", ft.Icons.DESCRIPTION, "/report"),
                    ft.Container(expand=True),
                ], spacing=8),
            ], spacing=10),
            padding=ft.padding.only(left=14, top=10, right=14, bottom=12),
            border=ft.border.only(top=ft.BorderSide(1, theme.border)))

        return ft.Column([hdr, ft.Container(self._chat, expand=True), inp],
                         spacing=0, expand=True)

    def _chip(self, label, icon, cmd):
        return ft.Container(
            ft.Row([ft.Icon(icon, size=12, color=theme.text_secondary),
                    ft.Text(label, size=11, color=theme.text_secondary, font_family=theme.font_family),
                    ], spacing=4),
            padding=ft.padding.only(left=10, top=5, right=10, bottom=5),
            border_radius=theme.radius_sm,
            border=ft.border.all(1, theme.border),
            on_click=lambda e, c=cmd: (setattr(self._input, 'value', c), self._input.focus()),
            ink=True)

    def _welcome(self):
        ff = theme.font_family
        return ft.Container(
            ft.Column([
                ft.Row([ft.Icon(ft.Icons.PSYCHOLOGY_OUTLINED, size=22, color=theme.type_removal_install),
                        ft.Text("AI 助手已就绪", size=14, weight=ft.FontWeight.W_600,
                                color=theme.text_primary, font_family=ff),
                        ], spacing=8),
                ft.Text("可以提问航空维护问题，我会检索知识库并结合 AI 推理回答。",
                        size=11, color=theme.text_disabled, font_family=ff),
            ], spacing=8),
            padding=16, bgcolor=theme.card, border_radius=theme.radius_md)

    # ═══════════════════════════════════════════════
    # 气泡宽度（跟随面板宽度）
    # ═══════════════════════════════════════════════

    @staticmethod
    def _is_error(text: str) -> bool:
        """检测是否为错误消息。"""
        return (
            text.startswith("Error:")
            or text.startswith("[Error]")
            or "**AI 不可用**" in text
        )

    @property
    def _max_w(self) -> float:
        """气泡可用最大宽度。"""
        return max(200.0, (self.width or 520) - 32)

    def _rebuild_bubbles(self):
        """面板宽度变化时重建所有气泡。"""
        if not self._chat or not self._msg_pairs:
            return
        mw = self._max_w
        # 保留欢迎消息，替换后面的气泡
        controls = [self._chat.controls[0]]  # welcome
        for u, a, ts in self._msg_pairs:
            controls.append(timestamp_label(ts))
            controls.append(user_bubble(u, mw, on_copy=self._copy, on_refresh=self._refresh))
            controls.append(
                error_bubble(a, mw, on_copy=self._copy, on_refresh=self._refresh)
                if self._is_error(a)
                else ai_bubble(a, mw, on_copy=self._copy, on_refresh=self._refresh)
            )
        self._chat.controls = controls

    async def _scroll_to_bottom_async(self):
        """等 UI 刷新后滚到底部。"""
        import asyncio
        await asyncio.sleep(0.08)
        if self._chat and self._chat.controls:
            self._chat.scroll_to(offset=-1, duration=200)

    def _scroll_to_bottom(self):
        """sync 入口：通过 run_task 调度异步滚动。"""
        if self.page:
            self.page.run_task(self._scroll_to_bottom_async)

    def _copy(self, text: str):
        if self.page:
            self.page.set_clipboard(text)

    def _handle_send(self, txt: str):
        """ChatInput 回调：接收已提取的文本。"""
        if self._busy:
            return
        self._busy = True
        self._input.clear()

        mw = self._max_w
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")

        # 用户气泡
        self._chat.controls.append(timestamp_label(ts))
        self._chat.controls.append(user_bubble(txt, mw, on_copy=self._copy, on_refresh=self._refresh))

        # 加载指示（靠左）
        load = ft.Row([
            ft.Container(
                ft.Row([ft.ProgressRing(width=14, height=14, stroke_width=2, color=theme.info),
                        ft.Text("思考中...", size=11, color=theme.text_disabled, font_family=theme.font_family),
                        ], spacing=8),
                padding=ft.padding.only(left=16, top=10, right=16, bottom=10),
                border_radius=theme.radius_md, border=ft.border.all(1, theme.border)),
            ft.Container(expand=True),
        ])
        self._chat.controls.append(load)
        load_idx = len(self._chat.controls) - 1

        # 强制页面刷新 + 滚到底部，确保用户气泡立即出现
        self.page.update()
        self._scroll_to_bottom()

        self._txt, self._ts, self._load_idx = txt, ts, load_idx
        self.page.run_task(self._process)

    def _refresh(self, e):
        """重新生成：取出上一条用户消息重新发送。"""
        if self._busy or not self._msg_pairs:
            return
        last_user = self._msg_pairs[-1][0]
        self._input.value = last_user
        self._handle_send(last_user)

    async def _process(self):
        txt, ts, idx = self._txt, self._ts, self._load_idx
        self._busy = False

        # 将所有阻塞工作（RAG 检索 + LLM 调用）移到线程池，
        # 释放事件循环以处理窗口拖拽、面板缩放、动画等 UI 事件。
        import asyncio
        try:
            r = await asyncio.to_thread(self._do_work, txt)
        except Exception as ex:
            r = f"Error: {ex}"

        # 移除加载指示
        if idx < len(self._chat.controls):
            self._chat.controls.pop(idx)

        # 添加 AI / 错误气泡
        mw = self._max_w
        bubble = error_bubble(r, mw, on_copy=self._copy, on_refresh=self._refresh) \
            if self._is_error(r) \
            else ai_bubble(r, mw, on_copy=self._copy, on_refresh=self._refresh)
        self._chat.controls.append(bubble)
        self._msg_pairs.append((txt, r, ts))
        self._chat.update()
        await self._scroll_to_bottom_async()

    def _do_work(self, txt: str) -> str:
        """所有同步阻塞工作：命令路由 + RAG 检索 + LLM 调用。"""
        from app.ui.services.agent_service import AgentService
        if txt.startswith("/report"): return AgentService.get_daily_report()
        elif txt.startswith("/kb "): return AgentService.search_knowledge(txt[4:])
        elif txt.startswith("/compliance"): return "合规检查: 符合 AD/SB。"
        elif txt.startswith("/summary"): return AgentService.get_board_summary()
        else: return self._ask(txt)

    def _ask(self, q: str) -> str:
        from app.config.settings_manager import SettingsManager
        if not SettingsManager().load()["llm"].get("api_key"):
            return ("**AI 不可用**\n\n未配置 LLM API Key。\n请在设置中配置。\n\n"
                    "本地命令: /kb /report /compliance /summary")
        from app.agent.orchestrator import agent
        return agent.ask(q)
