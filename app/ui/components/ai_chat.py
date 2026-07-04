"""AI 对话面板 — chat_bubble + ChatInput 组合。"""
from __future__ import annotations

from datetime import datetime
import flet as ft
from app.config.theme import theme, s
from app.ui.components.chat_bubble import user_bubble, ai_bubble, error_bubble, timestamp_label, prompt_bubble
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
        self._task_card: ft.Container | None = None     # 任务进度卡片
        self._cancel_event = None                        # 取消事件
        self._proposal_results: list[tuple] = []         # 已处理的提案 (tid, result, title)
        self._status_bubbles: list[tuple] = []           # 状态气泡 (text, color) — 始终渲染在末尾

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
        if self._busy:
            return
        from app.ui.services.agent_service import AgentService
        AgentService.clear_session(self._session_id)
        self._session_id = self._new_session()
        self._msg_pairs.clear()
        self._proposal_results.clear()
        self._status_bubbles.clear()
        if self._chat:
            self._chat.controls.clear()
            self._chat.update()

    def resize(self, delta: float):
        new_w = max(self.MIN_W, min(self.MAX_W, self.width - delta))
        if new_w != self.width:
            self.width = new_w
            if not self._busy and not self.is_task_running:
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
                              style=ft.ButtonStyle(
                                  bgcolor=ft.Colors.TRANSPARENT,
                                  overlay_color=ft.Colors.RED_900,
                                  shape=ft.RoundedRectangleBorder(radius=s(4))),
                              on_click=lambda e: self.close()),
            ], spacing=8),
            padding=ft.padding.only(left=14, top=6, right=4, bottom=6),
            border=ft.border.only(bottom=ft.BorderSide(1, theme.border)))

        self._chat = ft.ListView(
            [], spacing=10, expand=True,
            padding=ft.padding.only(left=12, top=10, right=12, bottom=10),
        )

        # 任务进度卡片区域（固定在聊天区上方，不随滚动）
        self._task_area = ft.Container(visible=False, padding=ft.padding.only(left=12, top=4, right=12, bottom=0))

        self._input = ChatInput(on_send=self._handle_send, on_stop=self._handle_stop)

        # 严格/普通模式标签（点击切换，单标签明确当前状态）
        self._mode_label = ft.Text(
            self._mode_text(), size=12, weight=ft.FontWeight.W_600,
            color=theme.priority_cat_a if self._strict_mode else theme.info,
            font_family=ff,
        )
        self._mode_btn = ft.Container(
            ft.Row([
                ft.Icon(ft.Icons.SHIELD_OUTLINED if self._strict_mode else ft.Icons.LANGUAGE_OUTLINED,
                        size=13, color=self._mode_label.color),
                self._mode_label,
            ], spacing=4),
            padding=ft.padding.only(left=9, top=5, right=9, bottom=5),
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
                    self._chip("合规检查", ft.Icons.VERIFIED_USER, "/compliance"),
                    ft.Container(expand=True),
                ], spacing=8),
            ], spacing=8),
            padding=ft.padding.only(left=14, top=10, right=14, bottom=12),
            border=ft.border.only(top=ft.BorderSide(1, theme.border)))

        return ft.Column([hdr, self._task_area, ft.Container(self._chat, expand=True), inp],
                         spacing=0, expand=True)

    def _chip(self, label, icon, cmd):
        return ft.Container(
            ft.Row([ft.Icon(icon, size=13, color=theme.text_secondary),
                    ft.Text(label, size=12, color=theme.text_secondary, font_family=theme.font_family),
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
            if u == "__PROMPT__":
                controls.append(prompt_bubble(a, mw, on_copy=self._copy, on_refresh=self._refresh))
            elif u.startswith("__STATUS_"):
                pass  # 状态气泡在末尾统一渲染
            elif u.startswith("__AI_ONLY__"):
                controls.append(
                    error_bubble(a, mw, on_copy=self._copy, on_refresh=self._refresh)
                    if self._is_error(a)
                    else ai_bubble(a, mw, on_copy=self._copy, on_refresh=self._refresh)
                )
            else:
                controls.append(user_bubble(u, mw, on_copy=self._copy, on_refresh=self._refresh))
                controls.append(
                    error_bubble(a, mw, on_copy=self._copy, on_refresh=self._refresh)
                    if self._is_error(a)
                    else ai_bubble(a, mw, on_copy=self._copy, on_refresh=self._refresh)
                )

        # ── 提案 UI（活跃 + 已处理）──
        from app.core.state import state as app_state
        proposed = [t for t in app_state.get_all_tasks() if t.ai_proposed]
        if proposed:
            controls.append(self._build_proposal_actions(proposed, mw))
        for tid, result, title in self._proposal_results:
            controls.append(self._build_resolved_row(tid, result, title))

        # ── 状态气泡始终在最末尾 ──
        for text, color in self._status_bubbles:
            controls.append(_status_bubble(text, color, mw))

        self._chat.controls = controls

    def _build_resolved_row(self, tid, result, title):
        """重建已处理的提案结果行。"""
        color = theme.success if result == "accepted" else theme.error
        label = "已接受" if result == "accepted" else "已拒绝"
        return ft.Container(
            ft.Row([
                ft.Icon(ft.Icons.CHECK if result == "accepted" else ft.Icons.CLOSE,
                        size=s(12), color=color),
                ft.Text(f"{label}: {title[:25]}", size=s(11),
                        color=theme.text_secondary, font_family=theme.font_family),
            ], spacing=s(6)),
            border=ft.border.all(1, ft.Colors.with_opacity(0.15, color)),
            bgcolor=ft.Colors.with_opacity(0.04, color),
            border_radius=s(4),
            padding=ft.padding.symmetric(horizontal=s(8), vertical=s(4)),
        )

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

    def _build_proposal_actions(self, proposed, mw):
        """构建 AI 任务建议的接受/拒绝按钮条。"""
        from app.core.state import state as app_state
        ff = theme.font_family
        items = []
        self._proposal_rows = {}  # tid → Container
        for t in proposed:
            row = ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.TASK_ALT_OUTLINED, size=s(12), color=theme.info),
                    ft.Text(t.title[:25], size=s(11), color=theme.text_primary, font_family=ff),
                    ft.Container(expand=True),
                    ft.TextButton("接受", style=ft.ButtonStyle(
                        color=theme.success, padding=ft.padding.symmetric(horizontal=s(6)),
                        text_style=ft.TextStyle(size=s(10), font_family=ff)),
                        on_click=lambda e, tid=t.id: self._accept_proposal(tid)),
                    ft.TextButton("拒绝", style=ft.ButtonStyle(
                        color=theme.error, padding=ft.padding.symmetric(horizontal=s(6)),
                        text_style=ft.TextStyle(size=s(10), font_family=ff)),
                        on_click=lambda e, tid=t.id: self._reject_proposal(tid)),
                ], spacing=s(4), tight=True),
                bgcolor=ft.Colors.with_opacity(0.06, theme.info),
                border=ft.border.all(1, ft.Colors.with_opacity(0.2, theme.info)),
                border_radius=s(6),
                padding=ft.padding.all(s(8)),
                width=mw,
            )
            self._proposal_rows[t.id] = row
            items.append(row)
        if not items:
            return ft.Container(height=0)

        # 批量按钮
        self._batch_row = ft.Row([
            ft.ElevatedButton("接受全部", icon=ft.Icons.DONE_ALL,
                style=ft.ButtonStyle(bgcolor=theme.success, color=ft.Colors.WHITE,
                    shape=ft.RoundedRectangleBorder(radius=s(6)),
                    padding=ft.padding.symmetric(horizontal=s(12), vertical=s(4)),
                    text_style=ft.TextStyle(size=s(10), font_family=ff)),
                on_click=lambda e: self._accept_all_proposals()),
            ft.OutlinedButton("拒绝全部", icon=ft.Icons.CLOSE,
                style=ft.ButtonStyle(color=theme.error,
                    side=ft.BorderSide(1, theme.error),
                    shape=ft.RoundedRectangleBorder(radius=s(6)),
                    padding=ft.padding.symmetric(horizontal=s(12), vertical=s(4)),
                    text_style=ft.TextStyle(size=s(10), font_family=ff)),
                on_click=lambda e: self._reject_all_proposals()),
        ], spacing=s(8))
        items.append(self._batch_row)
        return ft.Column(items, spacing=s(6), tight=True)

    def _accept_proposal(self, tid):
        from app.ui.services.proposal_handler import ProposalHandler
        t = ProposalHandler.accept(tid)
        self._update_proposal_row(tid, "accepted", t.title)
        if self.page and t.title:
            try:
                from app.ui.widgets.toast import Toast
                Toast.show(self.page, "任务已接受", "success")
            except Exception:
                pass

    def _reject_proposal(self, tid):
        from app.ui.services.proposal_handler import ProposalHandler
        t = ProposalHandler.reject(tid)
        self._update_proposal_row(tid, "rejected", t.title)

    def _update_proposal_row(self, tid, result, title):
        """就地更新提案行：隐藏按钮，显示结果。"""
        row = self._proposal_rows.get(tid)
        if row is None:
            return
        try:
            color = theme.success if result == "accepted" else theme.error
            label = "已接受" if result == "accepted" else "已拒绝"
            row.content = ft.Row([
                ft.Icon(ft.Icons.CHECK if result == "accepted" else ft.Icons.CLOSE,
                        size=s(12), color=color),
                ft.Text(f"{label}: {title[:25]}", size=s(11),
                        color=theme.text_secondary, font_family=theme.font_family),
            ], spacing=s(6))
            row.border = ft.border.all(1, ft.Colors.with_opacity(0.15, color))
            row.bgcolor = ft.Colors.with_opacity(0.04, color)
            row.update()
            del self._proposal_rows[tid]
            self._proposal_results.append((tid, result, title))
            self._update_batch_buttons()
        except Exception:
            pass

    def _update_batch_buttons(self):
        """如果所有提案都已处理，隐藏批量按钮。"""
        from app.core.state import state as app_state
        remaining = [t for t in app_state.get_all_tasks() if t.ai_proposed]
        if not remaining and hasattr(self, '_batch_row') and self._batch_row:
            self._batch_row.visible = False
            try:
                self._batch_row.update()
            except Exception:
                pass

    def _accept_all_proposals(self):
        from app.ui.services.proposal_handler import ProposalHandler
        results = ProposalHandler.accept_all()
        for r in results:
            self._update_proposal_row(r.task_id, "accepted", r.title)
        self._update_batch_buttons()
        if self.page:
            from app.ui.widgets.toast import Toast
            Toast.show(self.page, "全部任务已接受", "success")

    def _reject_all_proposals(self):
        from app.ui.services.proposal_handler import ProposalHandler
        results = ProposalHandler.reject_all()
        for r in results:
            self._update_proposal_row(r.task_id, "rejected", r.title)
        self._update_batch_buttons()
        if self.page:
            from app.ui.widgets.toast import Toast
            Toast.show(self.page, "已取消全部验收建议", "info")
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

        # 检测 AI 是否创建了幽灵任务，添加接受/拒绝按钮
        from app.core.state import state as app_state
        proposed = [t for t in app_state.get_all_tasks() if t.ai_proposed]
        if proposed:
            self._chat.controls.append(self._build_proposal_actions(proposed, mw))

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

    # ═══════════════════════════════════════════════
    # 任务进度卡片（替换 _show_ai_in_panel 的重复气泡）
    # ═══════════════════════════════════════════════

    def show_task_card(self, title: str, on_cancel=None):
        """在聊天区顶部显示任务进度卡片。"""
        import threading
        self._cancel_event = threading.Event()
        ff = theme.font_family

        self._status_text = ft.Text("正在准备...", size=s(11), color=theme.text_secondary, font_family=ff)
        self._task_spinner = ft.ProgressRing(width=s(14), height=s(14), color=theme.info)

        cancel_btn = ft.TextButton("取消", icon=ft.Icons.CANCEL_OUTLINED,
            style=ft.ButtonStyle(color=theme.text_secondary,
                padding=ft.padding.symmetric(horizontal=s(8), vertical=s(2)),
                text_style=ft.TextStyle(size=s(10), font_family=ff)),
            on_click=lambda e: self._cancel_task(on_cancel))

        self._task_card = ft.Container(
            ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.PSYCHOLOGY_OUTLINED, size=s(15), color=theme.info),
                    ft.Text(title, size=s(13), weight=ft.FontWeight.W_600,
                            color=theme.text_primary, font_family=ff),
                    ft.Container(expand=True),
                    cancel_btn,
                ], spacing=s(6)),
                ft.Container(height=s(4)),
                ft.Row([self._task_spinner, self._status_text], spacing=s(8)),
            ], spacing=0, tight=True),
            bgcolor="#111111", border_radius=s(8),
            border=ft.border.all(1, theme.info),
            padding=ft.padding.all(s(10)),
        )

        self._task_area.content = self._task_card
        self._task_area.visible = True
        try: self._task_area.update()
        except Exception: pass

    def update_task_card(self, status: str, border_color: str = None):
        """更新任务卡片的进度文字和边框颜色。"""
        if self._task_card and hasattr(self, '_status_text'):
            self._status_text.value = status
            try: self._status_text.update()
            except Exception: pass
        if border_color and self._task_card:
            self._task_card.border = ft.border.all(1, border_color)
            try: self._task_card.update()
            except Exception: pass

    def mark_task_done(self):
        """将取消按钮改为「完成」按钮（审阅类工具用）。"""
        if not self._task_card: return
        col = self._task_card.content
        header_row = col.controls[0]  # first Row: icon + title + expand + cancel_btn
        header_row.controls[-1] = ft.TextButton("完成", icon=ft.Icons.CHECK_OUTLINED,
            style=ft.ButtonStyle(color=theme.success,
                padding=ft.padding.symmetric(horizontal=s(8), vertical=s(2)),
                text_style=ft.TextStyle(size=s(10), font_family=theme.font_family)),
            on_click=lambda e: self.hide_task_card())
        try: self._task_card.update()
        except Exception: pass

    def hide_task_card(self, cancelled: bool = False):
        """移除任务进度卡片。"""
        from app.agent.active_task import active_task_registry
        active_task_registry.clear()
        self._task_card = None
        self._cancel_event = None
        self._task_area.visible = False
        self._task_area.content = None
        try: self._task_area.update()
        except Exception: pass

    def show_prompt_bubble(self, text: str):
        """显示紫色「需要补充信息」提示气泡。追加不重建。"""
        from datetime import datetime
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        self._msg_pairs.append(("__PROMPT__", text, ts))
        if self._chat is not None:
            self._chat.controls.append(timestamp_label(ts))
            self._chat.controls.append(prompt_bubble(text, self._max_w,
                                       on_copy=self._copy, on_refresh=self._refresh))
            try: self._chat.update()
            except Exception: pass
        self._scroll_to_bottom()

    def show_status_bubble(self, text: str, color: str = "#5294e2"):
        """显示彩色状态气泡（完成/取消等）。始终追加到最末尾。"""
        self._status_bubbles.append((text, color))
        if self._chat is not None:
            self._chat.controls.append(_status_bubble(text, color, self._max_w))
            try: self._chat.update()
            except Exception: pass
        self._scroll_to_bottom()

    def _cancel_task(self, on_cancel=None):
        """取消当前任务——设置取消信号 + 通知回调（回调负责清理幽灵卡片和状态栏）。"""
        if self._cancel_event:
            self._cancel_event.set()
        self.update_task_card("已取消", border_color="#666666")
        if on_cancel:
            on_cancel()

    @property
    def is_task_running(self) -> bool:
        return self._task_card is not None and self._cancel_event is not None

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


def _status_bubble(text: str, color: str, max_w: float) -> ft.Container:
    """彩色状态提示条 — 完成(绿)/取消(灰)等。"""
    return ft.Container(
        ft.Row([
            ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE if "完成" in text else ft.Icons.CANCEL_OUTLINED,
                    size=13, color=color),
            ft.Text(text, size=11, color=color, font_family=theme.font_family,
                    weight=ft.FontWeight.W_600),
        ], spacing=8, alignment=ft.MainAxisAlignment.CENTER),
        bgcolor=ft.Colors.with_opacity(0.08, color),
        border=ft.border.all(1, ft.Colors.with_opacity(0.2, color)),
        border_radius=s(6),
        padding=ft.padding.symmetric(horizontal=s(12), vertical=s(8)),
        width=min(max_w, 400),
    )
