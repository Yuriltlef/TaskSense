"""AI 对话面板 — chat_bubble + ChatInput 组合。"""
from __future__ import annotations

from datetime import datetime
import flet as ft
from app.config.theme import theme, s
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
        self._cancelled = False
        self._msg_pairs: list[tuple[str, str, str]] = []  # (user, ai, timestamp)
        self._session_id = self._new_session()
        self._strict_mode = False  # False=普通 True=严格

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

    @staticmethod
    def _new_session() -> str:
        import uuid
        return uuid.uuid4().hex[:8]

    def _reset_chat(self):
        from app.ui.services.agent_service import AgentService
        AgentService.clear_session(self._session_id)
        self._session_id = self._new_session()
        self._msg_pairs.clear()
        if self._chat:
            self._chat.controls.clear()
            self._chat.update()

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
                ft.IconButton(ft.Icons.ADD_COMMENT_OUTLINED, icon_size=16,
                              icon_color=theme.text_secondary, tooltip="新对话",
                              on_click=lambda e: self._reset_chat()),
                ft.IconButton(ft.Icons.CLOSE, icon_size=16, icon_color=theme.text_secondary,
                              on_click=lambda e: self.close()),
            ], spacing=8),
            padding=ft.padding.only(left=14, top=6, right=4, bottom=6),
            border=ft.border.only(bottom=ft.BorderSide(1, theme.border)))

        self._chat = ft.ListView(
            [], spacing=10, expand=True,
            padding=ft.padding.only(left=12, top=10, right=12, bottom=10),
        )

        self._input = ChatInput(on_send=self._handle_send, on_stop=self._handle_stop)

        # 严格/普通模式标签（点击切换，单标签明确当前状态）
        self._mode_label = ft.Text(
            self._mode_text(), size=10, weight=ft.FontWeight.W_600,
            color=theme.priority_cat_a if self._strict_mode else theme.info,
            font_family=ff,
        )
        self._mode_btn = ft.Container(
            ft.Row([
                ft.Icon(ft.Icons.SHIELD_OUTLINED if self._strict_mode else ft.Icons.LANGUAGE_OUTLINED,
                        size=12, color=self._mode_label.color),
                self._mode_label,
            ], spacing=4),
            padding=ft.padding.only(left=8, top=4, right=8, bottom=4),
            border_radius=theme.radius_sm,
            border=ft.border.all(1, theme.border),
            on_click=lambda e: self._toggle_mode(),
            ink=True,
        )

        inp = ft.Container(
            ft.Column([
                self._input,
                ft.Row([
                    self._mode_btn,
                    self._chip("搜索知识库", ft.Icons.SEARCH, "/kb "),
                    self._chip("生成报告", ft.Icons.DESCRIPTION, "/report"),
                    self._chip("看板摘要", ft.Icons.DASHBOARD, "/summary"),
                    self._chip("合规检查", ft.Icons.VERIFIED_USER, "/compliance"),
                ], spacing=s(6), wrap=True),
            ], spacing=s(8)),
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

    def _mode_text(self) -> str:
        return "严格模式" if self._strict_mode else "普通模式"

    def _toggle_mode(self):
        self._strict_mode = not self._strict_mode
        self._mode_label.value = self._mode_text()
        self._mode_label.color = theme.priority_cat_a if self._strict_mode else theme.info
        self._mode_btn.content.controls[0].name = (
            ft.Icons.SHIELD_OUTLINED if self._strict_mode else ft.Icons.LANGUAGE_OUTLINED
        )
        self._mode_btn.content.controls[0].color = self._mode_label.color
        self._mode_btn.update()

    # ═══════════════════════════════════════════════
    # 气泡宽度（跟随面板宽度）
    # ═══════════════════════════════════════════════

    @staticmethod
    def _is_error(text: str) -> bool:
        return (
            text.startswith("Error:")
            or text.startswith("[Error]")
            or "**AI 不可用**" in text
            or "**AI 正在初始化**" in text
            or text == "回答已中断"
        )

    @property
    def _max_w(self) -> float:
        return max(200.0, (self.width or 520) - 32)

    def _rebuild_bubbles(self):
        if not self._chat or not self._msg_pairs:
            return
        mw = self._max_w
        controls = []
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
        import asyncio
        await asyncio.sleep(0.08)
        if self._chat and self._chat.controls:
            self._chat.scroll_to(offset=-1, duration=200)

    def _scroll_to_bottom(self):
        if self.page:
            self.page.run_task(self._scroll_to_bottom_async)

    def _copy(self, text: str):
        if self.page:
            self.page.set_clipboard(text)

    def _model_ready(self) -> bool:
        from app.agent.preload import is_preload_done
        return is_preload_done()

    # ═══════════════════════════════════════════════
    # 发送 / 中断
    # ═══════════════════════════════════════════════

    def _handle_send(self, txt: str):
        if self._busy:
            return

        mw = self._max_w
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")

        # 模型未就绪
        if not self._model_ready():
            self._chat.controls.append(timestamp_label(ts))
            self._chat.controls.append(user_bubble(txt, mw, on_copy=self._copy, on_refresh=self._refresh))
            self._chat.controls.append(error_bubble(
                "**AI 正在初始化**\n\n嵌入模型仍在加载中，请稍后再试。", mw))
            self._input.clear()
            self._chat.update()
            self._scroll_to_bottom()
            return

        self._busy = True
        self._cancelled = False
        self._input.set_busy(True)
        self._input.clear()

        self._chat.controls.append(timestamp_label(ts))
        self._chat.controls.append(user_bubble(txt, mw, on_copy=self._copy, on_refresh=self._refresh))

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

        self.page.update()
        self._scroll_to_bottom()

        self._txt, self._ts, self._load_idx = txt, ts, load_idx
        self.page.run_task(self._process)

    def _handle_stop(self):
        """用户点击中止按钮 — 立即通知后台线程停止。"""
        self._cancelled = True
        if hasattr(self, '_cancel_event') and self._cancel_event:
            self._cancel_event.set()

    def _refresh(self, e):
        if self._busy or not self._msg_pairs:
            return
        last_user = self._msg_pairs[-1][0]
        self._input.value = last_user
        self._handle_send(last_user)

    async def _process(self):
        txt, ts, idx = self._txt, self._ts, self._load_idx
        import asyncio, concurrent.futures, threading

        cancel_event = threading.Event()
        self._cancel_event = cancel_event

        # 在线程池执行阻塞工作，但不阻塞事件循环
        loop = asyncio.get_running_loop()
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = loop.run_in_executor(executor, self._do_work, txt, cancel_event)

        # 轮询等待，每 0.15s 检查一次取消标志
        r = None
        try:
            while not future.done():
                await asyncio.sleep(0.15)
                if self._cancelled:
                    cancel_event.set()
                    # future 仍在运行但结果被丢弃
                    r = "回答已中断"
                    break
            if r is None:
                r = future.result()
        except Exception as ex:
            r = f"Error: {ex}"
        finally:
            executor.shutdown(wait=False)

        # 移除加载指示
        if idx < len(self._chat.controls):
            self._chat.controls.pop(idx)

        # 添加气泡
        mw = self._max_w
        bubble = error_bubble(r, mw, on_copy=self._copy, on_refresh=self._refresh) \
            if self._is_error(r) \
            else ai_bubble(r, mw, on_copy=self._copy, on_refresh=self._refresh)
        self._chat.controls.append(bubble)
        self._msg_pairs.append((txt, r, ts))

        self._busy = False
        self._cancel_event = None
        self._input.set_busy(False)
        self._chat.update()
        await self._scroll_to_bottom_async()

    def _do_work(self, txt: str, cancel_event) -> str:
        from app.ui.services.agent_service import AgentService
        if cancel_event.is_set():
            return "回答已中断"
        if txt.startswith("/report"): return AgentService.get_daily_report()
        elif txt.startswith("/kb "): return AgentService.search_knowledge(txt[4:])
        elif txt.startswith("/compliance"): return "合规检查: 符合 AD/SB。"
        elif txt.startswith("/summary"): return AgentService.get_board_summary()
        else: return self._ask(txt, cancel_event)

    def _ask(self, q: str, cancel_event) -> str:
        from app.config.settings_manager import SettingsManager
        if not SettingsManager().load()["llm"].get("api_key"):
            return ("**AI 不可用**\n\n未配置 LLM API Key。\n请在设置中配置。\n\n"
                    "本地命令: /kb /report /compliance /summary")
        if cancel_event.is_set():
            return "回答已中断"

        from app.ui.services.agent_service import AgentService
        return AgentService.ask(q, self._session_id, strict=self._strict_mode,
                               cancel_event=cancel_event)
