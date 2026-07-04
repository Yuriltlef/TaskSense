"""看板主页面."""

from datetime import datetime, timedelta

import flet as ft

from app.config.theme import theme, s
from app.core.logging import log
from app.core.models.aircraft import Aircraft, AircraftStatus
from app.core.models.kanban import FilterState
from app.core.models.task import Priority
from app.core.services.board_service import board_service
from app.core.services.task_service import task_service
from app.core.state import state
from app.agent.active_task import active_task_registry
from app.ui.components.ai_suggestion import FleetStatusBar
from app.ui.components.command_bar import CommandBar
from app.ui.components.kanban_board import KanbanBoard
from app.ui.components.side_panel import SidePanel
from app.ui.components.ai_chat import AIChatPanel
from app.ui.components.bottom_status_bar import BottomStatusBar
from app.ui.widgets.toast import Toast
from app.ui.services.task_registry import TaskRegistry
from app.ui.services.dialog_builder import header as dlg_header, footer as dlg_footer, button_style as dlg_btn_style


class BoardPage:
    def __init__(self, api_ready: bool = False):
        self.api_ready = api_ready
        self.kanban_board: KanbanBoard | None = None
        self.side_panel: SidePanel | None = None
        self.ai_chat: AIChatPanel | None = None
        self.command_bar: CommandBar | None = None
        self.fleet_status: FleetStatusBar | None = None
        self.status_bar: BottomStatusBar | None = None
        self._page: ft.Page | None = None
        self._search_field: ft.TextField | None = None
        self._search_box: ft.Container | None = None
        self._drag_start_width: float | None = None
        self._drag_start_x: float | None = None
        self._agent_busy = False
        self._board_refresh_pending = False
        # ── 任务注册表（线程安全）──
        self._task_registry: TaskRegistry = TaskRegistry()
        self._report_result: str | None = None
        self._review_result: dict | None = None
        self._report_dlg = None               # OverlayDimmer ref
        self._review_dlg = None               # OverlayDimmer ref
        self._report_thread = None            # threading.Thread ref
        self._review_thread = None            # threading.Thread ref
        state.subscribe(self._on_state_changed)

    def build(self, page: ft.Page) -> ft.Container:
        self._page = page
        ff = theme.font_family

        self.kanban_board = KanbanBoard(
            on_card_click=self._on_card_click,
            on_card_context_menu=self._on_card_context_menu,
            on_drop=self._on_drop,
            on_column_menu=self._on_column_menu,
        )
        self.side_panel = SidePanel(on_close=self._on_side_panel_close,
                                     on_edit=self._on_edit_task)
        self.ai_chat = AIChatPanel(on_close=self._on_side_panel_close)
        self.command_bar = CommandBar(on_execute=self._on_command_execute)
        self.fleet_status = FleetStatusBar()
        self.status_bar = BottomStatusBar(
            on_task_click=self._on_status_task_click,
            on_task_cancel=self._on_status_task_cancel,
            on_report_click=self._on_status_report_click,
            on_review_click=self._on_status_review_click,
        )
        self._task_registry._on_change = self._refresh_status_bar

        # ── BoardRenderer 回调注册 ──
        from app.ui.services.board_renderer import BoardRenderer
        BoardRenderer.set_callbacks(self._make_ghost_callbacks)

        # ── 搜索字段（由 app.py 统一标题栏引用）──
        self._search_field = ft.TextField(
            hint_text="搜索任务、ATA 章节、飞机注册号...",
            border=ft.InputBorder.NONE,
            border_color=ft.Colors.TRANSPARENT,
            focused_border_color=ft.Colors.TRANSPARENT,
            filled=False,
            cursor_color="#5294e2",
            cursor_height=s(14),
            text_style=ft.TextStyle(color=theme.text_primary, size=s(13), font_family=ff),
            hint_style=ft.TextStyle(color=theme.text_secondary, size=s(12), font_family=ff),
            content_padding=ft.padding.only(left=s(2), top=0, right=s(2), bottom=0),
            dense=True,
            bgcolor=ft.Colors.TRANSPARENT,
            expand=True,
            on_change=self._on_search_input,
            on_submit=self._on_search_submit,
            on_focus=lambda e: self._on_search_focus(),
            on_blur=lambda e: self._on_search_blur(),
        )

        # ── 主布局（无顶栏，顶栏已合并到窗口标题栏）──
        main = ft.Container(
            content=ft.Column([
                self.fleet_status,
                ft.Row([
                    ft.Container(content=self.kanban_board, expand=True,
                                 bgcolor=theme.bg),
                    ft.GestureDetector(
                        content=ft.Container(width=5, bgcolor=theme.border),
                        mouse_cursor=ft.MouseCursor.RESIZE_LEFT_RIGHT,
                        on_horizontal_drag_start=self._on_drag_start,
                        on_horizontal_drag_update=self._on_panel_resize,
                    ),
                    self.side_panel,
                    self.ai_chat,
                ], spacing=0, expand=True),
                self.status_bar,
            ], spacing=0, expand=True),
            expand=True, bgcolor=theme.bg,
        )
        self._fill_board_from_state()
        self._refresh_status_bar()
        return main

    # ═══════════════════════ 数据 ═══════════════════════

    def _fill_board_from_state(self):
        from app.ui.services.board_renderer import BoardRenderer
        BoardRenderer.fill_board(self.kanban_board, self.fleet_status)

    def _make_ghost_callbacks(self, prop_type: str, tid: str, rec: str = ""):
        """为幽灵卡片创建 accept/reject 回调（根据提案类型分发）。"""
        if prop_type == "acceptance":
            return (
                lambda p, tid=tid, r=rec: self._accept_acceptance(tid, r),
                lambda p, tid=tid: self._reject_acceptance(tid),
            )
        return (
            lambda p, tid=tid: self._accept_ai_task(tid),
            lambda p, tid=tid: self._reject_ai_task(tid),
        )

    def _accept_ai_task(self, tid):
        """接受 AI 建议任务——委托 ProposalHandler 执行业务变更。"""
        t = state.get_task(tid)
        title = t.title if t else ""
        from app.ui.services.proposal_handler import ProposalHandler
        ProposalHandler.accept(tid)
        self._sync_chat_proposal(tid, "accepted", title)
        Toast.show(self._page, "AI 建议已接受", "success")
        self._refresh_board()

    def _reject_ai_task(self, tid):
        """拒绝 AI 建议任务——委托 ProposalHandler 执行业务变更。"""
        t = state.get_task(tid)
        title = t.title if t else ""
        from app.ui.services.proposal_handler import ProposalHandler
        ProposalHandler.reject(tid)
        self._sync_chat_proposal(tid, "rejected", title)
        Toast.show(self._page, "AI 建议已拒绝", "info")
        self._refresh_board()

    def _accept_acceptance(self, tid, recommendation):
        """用户确认验收建议——ProposalHandler 已执行业务变更，此处刷新 UI。"""
        t = state.get_task(tid)
        title = t.title if t else ""
        self._sync_chat_proposal(tid, "accepted", title)
        board_service.set_filters(FilterState())
        if recommendation == "approve":
            Toast.show(self._page, "验收通过，任务已移至已完成", "success")
        else:
            Toast.show(self._page, "验收驳回，任务已退回待处理", "info")
        self._refresh_board()

    def _reject_acceptance(self, tid):
        """用户取消验收建议——ProposalHandler 已执行业务变更，此处刷新 UI。"""
        t = state.get_task(tid)
        title = t.title if t else ""
        self._sync_chat_proposal(tid, "rejected", title)
        board_service.set_filters(FilterState())
        Toast.show(self._page, "已取消，任务保留在验收中", "info")
        self._refresh_board()

    def _sync_chat_proposal(self, tid: str, result: str, title: str):
        """同步 AI 对话面板中的提案行状态。"""
        # 幽灵卡片被处理后，始终检查是否有等待确认的任务需要完成
        self._check_ghost_pending_completion()
        # 更新对话面板（仅当打开时）
        if not self.ai_chat or not self.ai_chat.is_open:
            return
        try:
            if hasattr(self.ai_chat, '_proposal_results'):
                self.ai_chat._proposal_results.append((tid, result, title))
            if hasattr(self.ai_chat, '_rebuild_bubbles'):
                self.ai_chat._rebuild_bubbles()
                self.ai_chat.update()
        except Exception:
            pass

    def _check_ghost_pending_completion(self):
        """检查是否所有幽灵卡片都已处理，若是则完成等待中的任务卡片。"""
        proposed = [t for t in state.get_all_tasks() if t.ai_proposed]
        log.debug("ghost_check", f"proposed count={len(proposed)} ids={[t.id[:8] for t in proposed]}")
        if proposed:
            return
        # 所有幽灵卡片已处理 → 完成所有"等待确认"的状态栏任务
        for t in self._task_registry.get_all():
            if t.get("status") == "等待确认":
                self._task_registry.update_status(t["id"], "已完成", 1.0)
                # 如果对话区任务卡片还开着，关闭它
                if self.ai_chat:
                    try:
                        self.ai_chat.update_task_card("已完成", border_color=theme.success)
                    except Exception:
                        pass
                    import time, threading
                    def _delayed_hide():
                        time.sleep(2)
                        try:
                            self.ai_chat.hide_task_card()
                        except Exception:
                            pass
                    threading.Thread(target=_delayed_hide, daemon=True).start()
                # 延迟从状态栏移除
                def _delayed_unregister(tid=t["id"]):
                    import time
                    time.sleep(5)
                    self._task_registry.unregister(tid)
                import threading
                threading.Thread(target=_delayed_unregister, daemon=True).start()

    # load_demo_data() 已废弃 — 数据统一由 data/board_state.json 管理
    # 用 scripts/gen_demo_json.py 生成/重置 JSON

    # ═══════════════════════ 事件 ═══════════════════════

    def _on_state_changed(self):
        """50ms 防抖 + 主线程安全：合并连续变更为一次列级更新。"""
        if self._board_refresh_pending:
            return
        self._board_refresh_pending = True
        if self._page:
            self._page.run_task(self._debounced_refresh)

    async def _debounced_refresh(self):
        import asyncio
        await asyncio.sleep(0.05)
        self._board_refresh_pending = False
        self._refresh_board()

    def _refresh_board(self):
        try:
            from app.ui.widgets.context_menu import close_current_menu
            close_current_menu()
        except Exception:
            pass
        if not self.kanban_board:
            return
        from app.ui.services.board_renderer import BoardRenderer
        BoardRenderer.refresh_incremental(self.kanban_board, self.fleet_status)

    def _on_drag_start(self, e):
        """记录拖拽起始状态（面板宽度 + 光标绝对位置）。"""
        self._drag_start_x = e.global_x
        if self.ai_chat and self.ai_chat.is_open:
            self._drag_start_width = self.ai_chat.width
        elif self.side_panel and self.side_panel.is_open:
            self._drag_start_width = self.side_panel.width
        else:
            self._drag_start_width = None

    def _on_panel_resize(self, e):
        """基于绝对坐标位移调整面板宽度，消除增量 delta 的累积漂移。"""
        if self._drag_start_width is None or self._drag_start_x is None:
            return
        # 用 global_x 的绝对位移，不受布局重排影响
        delta = self._drag_start_x - e.global_x
        if self.ai_chat and self.ai_chat.is_open:
            new_w = max(self.ai_chat.MIN_W,
                       min(self.ai_chat.MAX_W,
                           self._drag_start_width + delta))
            if new_w != self.ai_chat.width:
                self.ai_chat.width = new_w
                if not self.ai_chat._busy and not self.ai_chat.is_task_running:
                    self.ai_chat._rebuild_bubbles()
                self.ai_chat.update()
        elif self.side_panel and self.side_panel.is_open:
            new_w = self._drag_start_width + delta
            if 280 <= new_w <= 1000:
                self.side_panel.width = new_w
                self.side_panel.update()

    def _on_card_click(self, tid):
        from app.ui.widgets.context_menu import close_current_menu
        close_current_menu()
        t = state.get_task(tid)
        if t and self.side_panel:
            if self.ai_chat and self.ai_chat.is_open: self.ai_chat.close()
            self.side_panel.toggle_task(t)
            self._page.update()

    def _open_ai_panel(self):
        if self.ai_chat:
            if self.side_panel and self.side_panel.is_open: self.side_panel.close()
            if not self.ai_chat.is_open:
                self.ai_chat.open()
            self._page.update()

    def _finish_task_card(self, label: str, status: str, color: str):
        """统一的任务卡片结束处理：停动画 + 显示结果气泡（保留在聊天历史）+ 延迟关闭卡片。"""
        import time, threading
        active_task_registry.clear()
        self.ai_chat.update_task_card(status, border_color=color)
        self.ai_chat.show_status_bubble(f"{label} {status}", color)
        # 更新状态栏
        task_id = self._task_registry.find_by_label(label)
        if task_id:
            is_ok = "完成" in status or "确认" in status
            self._task_registry.update_status(task_id, status, 1.0 if is_ok else 0)
        time.sleep(2)
        self.ai_chat.hide_task_card()
        # 5 秒后从状态栏移除
        if task_id:
            def _delayed_unregister():
                time.sleep(5)
                self._task_registry.unregister(task_id)
            threading.Thread(target=_delayed_unregister, daemon=True).start()

    # ── 以下方法已迁移到 TaskRegistry ──
    # register → self._task_registry.register()
    # unregister → self._task_registry.unregister()
    # update_status → self._task_registry.update_status()
    # find_by_label → self._task_registry.find_by_label()

    def _poll_ghost_resolution(self, label: str, pending_ids: set,
                                cancel_event, timeout: int = 300):
        """轮询等待幽灵任务全部确认/拒绝。cancel_event 由调用方传入。"""
        import time
        cancel = cancel_event
        if cancel is None:
            self._finish_task_card(label, "已取消", theme.text_disabled)
            return
        for i in range(timeout):
            if cancel and cancel.is_set():
                self._finish_task_card(label, "已取消", theme.text_disabled)
                return
            time.sleep(1)
            remaining = [tid for tid in pending_ids
                         if state.get_task(tid) and state.get_task(tid).ai_proposed]
            if len(remaining) == 0:
                self._finish_task_card(label, "全部已确认", theme.success)
                return
            if i % 5 == 0:
                self.ai_chat.update_task_card(f"{len(remaining)} 个待确认...", border_color=theme.warning)
                # 不需要每5秒刷新看板——幽灵卡片已在初始渲染中创建，仅在用户操作后状态变更时刷新
                pass
        self._finish_task_card(label, "等待超时", theme.text_disabled)

    # ═══════════════════════════════════════════
    # ── 任务注册表已迁移到 app/ui/services/task_registry.py ──
    # register / unregister / update_status / find_by_label → self._task_registry.xxx()
    # ═══════════════════════════════════════════

    def _refresh_status_bar(self):
        """刷新状态栏显示。"""
        if self.status_bar:
            try:
                self.status_bar.set_tasks(self._task_registry.get_all())
                self.status_bar.set_has_report(self._report_result is not None)
                self.status_bar.set_has_review(self._review_result is not None)
                self.status_bar.update()
            except Exception:
                pass

    def _on_status_task_click(self, task_id: str):
        """状态栏任务标签被点击 → 重新打开对应面板/弹窗。"""
        for t in self._task_registry.get_all():
            if t["id"] == task_id:
                ttype = t.get("type", "")
                if ttype == "report":
                    self._reopen_report_dlg()
                elif ttype == "review":
                    self._reopen_review_dlg()
                else:  # ai_panel
                    self._open_ai_panel()
                return

    def _on_status_task_cancel(self, task_id: str):
        """状态栏取消——立即清理幽灵卡片 + 更新 UI + 设取消事件。"""
        log.debug("cancel", f"ENTER task_id={task_id}")
        for t in self._task_registry.get_all():
            if t["id"] == task_id:
                ttype = t.get("type", "")
                log.debug("cancel", f"type={ttype}")
                if ttype == "report":
                    self._cancel_report()
                elif ttype == "review":
                    self._cancel_review()
                else:
                    if self.ai_chat:
                        ce = self._runner.get_cancel()
                        log.debug("cancel", f"ce={'SET' if ce else 'NONE'}")
                        if ce:
                            ce.set()
                            log.debug("cancel", f"event set, is_set={ce.is_set()}")
                        self.ai_chat.update_task_card("已取消", border_color=theme.text_disabled)
                    self._force_clear_all_ghosts(task_id)
                    self._reject_all_proposals(task_id)
                    self._task_registry.update_status(task_id, "已取消", 0)
                    import time, threading
                    def _finish():
                        time.sleep(2)
                        try:
                            if self.ai_chat:
                                self.ai_chat.hide_task_card()
                        except Exception:
                            pass
                        time.sleep(3)
                        self._task_registry.unregister(task_id)
                    threading.Thread(target=_finish, daemon=True).start()
                return
        log.debug("cancel", f"task_id not found in registry")

    def _force_clear_all_ghosts(self, task_id: str):
        """清除幽灵卡片标记——委托 CancelCoordinator。"""
        from app.ui.services.cancel_coordinator import CancelCoordinator
        affected = CancelCoordinator.clear_ghost(task_id)
        if affected:
            self._refresh_board()

    def _reject_all_proposals(self, task_id: str):
        """将 AI 对话区关联提案标记为已拒绝——委托 ProposalHandler。"""
        if not self.ai_chat or not hasattr(self.ai_chat, '_proposal_results'):
            return
        from app.ui.services.proposal_handler import ProposalHandler
        # 单任务 AI：拒绝指定任务
        for prefix in ("classify_", "schedule_", "review_"):
            if task_id.startswith(prefix):
                real_tid = task_id[len(prefix):]
                if real_tid:
                    ProposalHandler.reject(real_tid)
                    t = state.get_task(real_tid)
                    self.ai_chat._proposal_results.append(
                        (real_tid, "rejected", t.title if t else ""))
                    self._sync_proposal_ui()
                return
        # 批量 AI 工具：拒绝全部
        for r in ProposalHandler.reject_all():
            self.ai_chat._proposal_results.append(
                (r.task_id, "rejected", r.title))
        self._sync_proposal_ui()

    def _sync_proposal_ui(self):
        """刷新 AI 对话区提案 UI。"""
        try:
            if hasattr(self.ai_chat, '_rebuild_bubbles'):
                self.ai_chat._rebuild_bubbles()
                self.ai_chat.update()
        except Exception:
            pass

    def _on_status_report_click(self, _=None):
        """状态栏报告入口被点击。"""
        if self._report_result is not None:
            self._reopen_report_dlg()
        else:
            self._show_empty_result_dlg("report")

    def _on_status_review_click(self, _=None):
        """状态栏审核入口被点击。"""
        if self._review_result is not None:
            self._reopen_review_dlg()
        else:
            self._show_empty_result_dlg("review")

    def _show_empty_result_dlg(self, kind: str):
        """显示无结果弹窗。"""
        ff = theme.font_family
        label = "报告" if kind == "report" else "审核"
        icon = "📊" if kind == "report" else "🔍"
        btn_label = "生成新报告" if kind == "report" else "开始新审核"

        def _gen_new(e):
            dlg.close()
            if kind == "report":
                self._cmd_report()
            else:
                self._cmd_review()

        PW, PH = 400, 220
        page_w = self._page.width or 1280
        page_h = self._page.height or 900
        cx = max(0, (page_w - PW) // 2)
        cy = max(20, (page_h - PH) // 2)

        panel = ft.Container(
            ft.Column([
                ft.Container(height=s(30)),
                ft.Text(f"{icon} 当前无{label}结果", size=s(16),
                        color=theme.text_primary, font_family=ff,
                        text_align=ft.TextAlign.CENTER),
                ft.Container(height=s(8)),
                ft.Text(f"尚未生成{label}，点击下方按钮开始", size=s(12),
                        color=theme.text_secondary, font_family=ff,
                        text_align=ft.TextAlign.CENTER),
                ft.Container(height=s(20)),
                ft.Row([
                    ft.Container(expand=True),
                    ft.ElevatedButton(btn_label, on_click=_gen_new,
                        style=ft.ButtonStyle(
                            shape=ft.RoundedRectangleBorder(radius=s(6)),
                            padding=ft.padding.only(left=s(18), top=s(7), right=s(18), bottom=s(7)),
                            text_style=ft.TextStyle(size=s(12), font_family=ff),
                            bgcolor="#5294e2", color=ft.Colors.WHITE, elevation=0)),
                    ft.Container(width=s(8)),
                    ft.OutlinedButton("关闭", on_click=lambda e: dlg.close(),
                        style=ft.ButtonStyle(
                            shape=ft.RoundedRectangleBorder(radius=s(6)),
                            padding=ft.padding.only(left=s(18), top=s(7), right=s(18), bottom=s(7)),
                            text_style=ft.TextStyle(size=s(12), font_family=ff),
                            side=ft.BorderSide(1, theme.border),
                            color=theme.text_secondary)),
                    ft.Container(expand=True),
                ]),
            ], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            width=PW, height=PH, bgcolor=theme.surface, border_radius=s(10),
            border=ft.border.all(1, theme.border),
            shadow=ft.BoxShadow(spread_radius=1, blur_radius=20, color="#000000aa"),
            left=cx, top=cy,
        )
        from app.ui.widgets.overlay_dimmer import OverlayDimmer
        dlg = OverlayDimmer.open(self._page, panel, dim_opacity=0.4,
                                  on_dimmer_click=lambda: dlg.close())

    # ── 报表弹窗最小化相关 ──

    def _cancel_report(self):
        """取消报表任务。"""
        self._report_result = None
        if self._report_dlg:
            try: self._report_dlg.close()
            except Exception: pass
            self._report_dlg = None
        self._task_registry.unregister("report")
        self._refresh_status_bar()

    def _reopen_report_dlg(self):
        """重新打开报表弹窗（加载中或已完成）。"""
        self._cmd_report_show_result(None)

    # ── 审核弹窗最小化相关 ──

    def _cancel_review(self):
        """取消审核任务。"""
        self._review_result = None
        if self._review_dlg:
            try: self._review_dlg.close()
            except Exception: pass
            self._review_dlg = None
        self._task_registry.unregister("review")
        self._refresh_status_bar()

    def _reopen_review_dlg(self):
        """重新打开审核弹窗（加载中或已完成）。"""
        self._cmd_review_show_result(None)

    def _on_side_panel_close(self):
        if self._page: self._page.update()

    def _on_edit_task(self, task):
        """从侧边栏编辑按钮触发的编辑弹窗。"""
        self._dlg_edit(task)

    # ═══════════════════════ 右键菜单 — 已迁移到 context_menu_builder.py ═══════════════════════

    def _on_card_context_menu(self, tid, x, y):
        from app.ui.widgets.context_menu import ContextMenu
        from app.ui.services.context_menu_builder import ContextMenuBuilder
        t = state.get_task(tid)
        if not t:
            return
        items = ContextMenuBuilder().build(t.status.value, t)
        if not items:
            return
        cx, cy = self._get_cursor_pos(self._page)
        ContextMenu(
            items=items,
            on_select=lambda a: self._card_action(tid, a),
        ).show(self._page, cx, cy)

    @staticmethod
    def _get_cursor_pos(page) -> tuple[float, float]:
        """Win32 API 获取鼠标在页面客户区内的坐标（不依赖 Flet 事件）。"""
        import ctypes
        from ctypes import wintypes
        try:
            pt = wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            hwnd = ctypes.windll.user32.FindWindowW(None, "TaskSense")
            if hwnd:
                ctypes.windll.user32.ScreenToClient(hwnd, ctypes.byref(pt))
            return (float(pt.x), float(pt.y))
        except Exception:
            return (100.0, 100.0)

    # ── 拖放内容补充 ──

    _INFO_GATES = {
        "backlog": {"triage": "_dlg_priority"},
        "triage": {"scheduled": "_dlg_schedule"},
    }

    def _on_drop(self, tid, col, index=-1):
        task = state.get_task(tid)
        src_col = task.status.value if task else None
        if src_col and col in self._INFO_GATES.get(src_col, {}):
            method = getattr(self, self._INFO_GATES[src_col][col])
            method(tid, col, index)
            return
        try:
            task_service.move_task(tid, col, index=index)
            if index >= 0:
                Toast.show(self._page, "已重新排序", "success")
            else:
                Toast.show(self._page, f"已移动到 {col}", "success")
        except Exception as e:
            Toast.show(self._page, str(e), "warning")

    def _dlg_priority(self, tid, col=None, index=-1):
        """确认优先级弹窗（复用自拖放流程）。
        col=None → 仅更新优先级不移动列；col 有值 → 设优先级并 move 到目标列。
        """
        ff = theme.font_family
        options = [
            ("aog", "AOG", "立即排故", theme.priority_aog),
            ("cat_a", "Cat A", "当日完成", theme.priority_cat_a),
            ("cat_b", "Cat B", "72 小时内", theme.priority_cat_b),
            ("cat_c", "Cat C", "10 天内", theme.priority_cat_c),
            ("cat_d", "Cat D", "120 天内", theme.priority_cat_d),
        ]
        # 初始选中当前任务的优先级
        t = state.get_task(tid)
        current_pri = t.priority.value if t else "cat_c"
        init_val = current_pri if current_pri in [o[0] for o in options] else "cat_c"
        selected = {"val": init_val}

        chips = []
        for val, label, desc, color in options:
            sel = val == selected["val"]
            chips.append(ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Icon(ft.Icons.FLAG_OUTLINED, size=s(14), color=color),
                        ft.Text(label, size=s(13),
                                weight=ft.FontWeight.W_600,
                                color=color if sel else theme.text_primary,
                                font_family=ff),
                    ], spacing=s(6)),
                    ft.Text(desc, size=s(11),
                            color=theme.text_secondary, font_family=ff),
                ], spacing=s(2), tight=True),
                padding=ft.padding.all(s(10)),
                border_radius=s(6),
                border=ft.border.all(
                    1.5, color if sel else theme.border),
                bgcolor=ft.Colors.with_opacity(0.06, color) if sel else theme.card,
                on_click=lambda e, v=val: _select(v),
                ink=True,
                width=150,
            ))

        def _select(v):
            selected["val"] = v
            for i, chip in enumerate(chips):
                s_sel = options[i][0] == v
                clr = options[i][3]
                chip.border = ft.border.all(
                    1.5, clr if s_sel else theme.border)
                chip.bgcolor = ft.Colors.with_opacity(
                    0.06, clr) if s_sel else theme.card
                row = chip.content.controls[0]
                row.controls[1].color = clr if s_sel else theme.text_primary
                chip.update()

        def _confirm(_):
            priority = selected["val"]
            try:
                from app.core.models.task import Priority
                task_service.update_task(tid, priority=Priority(priority))
                if col is not None:
                    task_service.move_task(tid, col, index=index)
                    labels = {"aog": "AOG", "cat_a": "Cat A", "cat_b": "Cat B",
                              "cat_c": "Cat C", "cat_d": "Cat D"}
                    Toast.show(self._page,
                               f"已分类 — {labels.get(priority, priority)}",
                               "success")
                else:
                    Toast.show(self._page, "优先级已更新", "success")
            except Exception as e:
                Toast.show(self._page, str(e), "warning")
            dlg.close()

        from app.ui.components.modal_dialog import ModalDialog

        form = ft.Container(
            ft.Column([
                ft.Row(chips[:3], spacing=s(8),
                       alignment=ft.MainAxisAlignment.CENTER),
                ft.Row(chips[3:], spacing=s(8),
                       alignment=ft.MainAxisAlignment.CENTER),
            ], spacing=s(8), tight=True),
            padding=ft.padding.all(s(14)),
        )

        content = ft.Column([
            dlg_header(ft.Icons.FLAG_OUTLINED, "确认优先级",
                       lambda e: dlg.close()),
            form,
            dlg_footer("取消", "确认", _confirm,
                       on_cancel=lambda e: dlg.close()),
        ], spacing=0, tight=True)
        dlg = ModalDialog(self._page, content, width=540)
        dlg.open()

    def _dlg_schedule(self, tid, col=None, index=-1, move_to=True):
        """排程弹窗。col/move_to=True → 设排程并移动到目标列；move_to=False → 仅更新排程不移动。"""
        ff = theme.font_family

        def _field(hint="", width=None):
            from app.ui.services.dialog_builder import make_field
            return make_field(hint=hint, width=width)

        def _label(text, required=False):
            from app.ui.services.dialog_builder import make_label
            return make_label(text, required)

        def _col(lbl, ctrl):
            from app.ui.services.dialog_builder import make_col
            return make_col(lbl, ctrl)

        hours_f = _field("计划工时 (h)，如 4.5", width=220)
        assignee_id_f = _field("员工 ID，如 ZH001")
        assignee_name_f = _field("姓名，如 张工")
        start_hour_f = _field("08", width=s(62))
        start_min_f = _field("30", width=s(62))
        due_hour_f = _field("08", width=s(62))
        due_min_f = _field("30", width=s(62))

        # ── 输入校验 ──
        def _clamp_tf(tf, hi):
            from app.ui.services.dialog_builder import clamp_time_field
            clamp_time_field(tf, hi); tf.update()
        for _tf, _hi in [(start_hour_f, 23), (start_min_f, 59),
                          (due_hour_f, 23), (due_min_f, 59)]:
            _tf.on_blur = lambda e, t=_tf, h=_hi: _clamp_tf(t, h)

        from app.ui.services.dialog_builder import make_date_picker as _mkdp

        # ── 预填任务已有的计划时间/人员 ──
        t = state.get_task(tid)
        start_date_ctrl, start_date_state, start_date_err, start_date_clr = _mkdp(
            self._page, t.planned_start if t else None, on_pick_callback=lambda: _recalc())
        due_date_ctrl, due_date_state, due_date_err, due_date_clr = _mkdp(
            self._page, t.planned_end if t else None, on_pick_callback=lambda: _recalc())
        if t:
            if t.planned_start:
                start_hour_f.value = t.planned_start.strftime("%H")
                start_min_f.value = t.planned_start.strftime("%M")
            if t.planned_end:
                due_hour_f.value = t.planned_end.strftime("%H")
                due_min_f.value = t.planned_end.strftime("%M")
            if t.estimated_hours:
                hours_f.value = str(t.estimated_hours)
            if t.employee_id:
                assignee_id_f.value = t.employee_id
            if t.employee_name:
                assignee_name_f.value = t.employee_name

        def _get_dt(date_state, h_f, m_f):
            from app.ui.services.dialog_builder import build_datetime
            return build_datetime(date_state, h_f, m_f)

        def _recalc():
            sd = _get_dt(start_date_state, start_hour_f, start_min_f)
            ed = _get_dt(due_date_state, due_hour_f, due_min_f)
            if sd and ed:
                diff = (ed - sd).total_seconds() / 3600
                if diff > 0:
                    hours_f.value = f"{diff:.1f}"; hours_f.update()
                else:
                    due_date_state["date"] = None
                    due_hour_f.value = ""; due_min_f.value = ""
                    try: due_hour_f.update(); due_min_f.update()
                    except Exception: pass
                    due_date_clr()
                    hours_f.value = ""
                    try: hours_f.update()
                    except Exception: pass
                    from app.ui.widgets.toast import Toast
                    Toast.show(self._page, "完成时间必须晚于开始时间", "warning")

        # 时/分字段 blur 时同步 clamp + 重算工时
        for _tf, _hi in [(start_hour_f, 23), (start_min_f, 59),
                          (due_hour_f, 23), (due_min_f, 59)]:
            _prev = _tf.on_blur
            _tf.on_blur = lambda e, t=_tf, h=_hi, p=_prev: (_clamp_tf(t, h), _recalc())

        def _confirm(_):
            from app.ui.widgets.toast import Toast
            start_dt = _get_dt(start_date_state, start_hour_f, start_min_f)
            due_dt = _get_dt(due_date_state, due_hour_f, due_min_f)
            hs = (hours_f.value or "").strip()
            aid = (assignee_id_f.value or "").strip()
            aname = (assignee_name_f.value or "").strip()
            start_date_clr(); due_date_clr()
            for c, h in [(hours_f, "计划工时 (h)，如 4.5"), (assignee_id_f, "员工 ID，如 ZH001"), (assignee_name_f, "姓名，如 张工")]:
                c.border_color = theme.border; c.hint_text = h
            if not start_dt: start_date_err("请选择开始日期"); return
            if not due_dt: due_date_err("请选择完成日期"); return
            if not hs: hours_f.border_color = theme.error; hours_f.hint_text = "请输入计划工时"; hours_f.update(); return
            if not aid: assignee_id_f.border_color = theme.error; assignee_id_f.hint_text = "请输入员工 ID"; assignee_id_f.update(); return
            if not aname: assignee_name_f.border_color = theme.error; assignee_name_f.hint_text = "请输入姓名"; assignee_name_f.update(); return
            try:
                if move_to and col:
                    task_service.move_task(tid, col, index=index)
                updates = {"assignee": f"{aid} {aname}"}
                try: updates["estimated_hours"] = float(hs)
                except: pass
                updates["due_date"] = due_dt
                task_service.update_task(tid, **updates)
                if move_to and col:
                    Toast.show(self._page, "已排程", "success")
                else:
                    Toast.show(self._page, "排程已更新", "success")
            except Exception as ex: Toast.show(self._page, str(ex), "warning")
            dlg.close()

        from app.ui.components.modal_dialog import ModalDialog
        header = dlg_header(ft.Icons.CALENDAR_MONTH_OUTLINED, "排程信息",
                            lambda e: dlg.close())
        sep=ft.Divider(height=s(12), color=ft.Colors.TRANSPARENT)
        def _date_row(label_text, date_ctrl, h_f, m_f):
            return ft.Column([
                _label(label_text, required=True),
                ft.Row([
                    ft.Container(content=date_ctrl, expand=True),
                    ft.Container(width=s(4)),
                    h_f, ft.Text("时", size=s(11), color=theme.text_secondary, font_family=ff),
                    m_f, ft.Text("分", size=s(11), color=theme.text_secondary, font_family=ff),
                ], spacing=s(4), vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ], spacing=s(4), tight=True)
        form=ft.Container(
            ft.Column([
                _date_row("计划开始日期", start_date_ctrl, start_hour_f, start_min_f), sep,
                _date_row("计划完成日期", due_date_ctrl, due_hour_f, due_min_f), sep,
                ft.Row([_col(_label("计划工时", required=True), hours_f), ft.Container(expand=True)], spacing=s(12)), sep,
                ft.Row([_col(_label("员工 ID", required=True), assignee_id_f), _col(_label("姓名", required=True), assignee_name_f)], spacing=s(12)),
            ], spacing=s(4), tight=True),
            padding=ft.padding.all(s(14)))
        footer = dlg_footer("取消", "确认排程", _confirm,
                            on_cancel=lambda e: dlg.close())
        content=ft.Column([header,form,footer],spacing=0,tight=True)
        dlg=ModalDialog(self._page,content,width=520)
        dlg.open()

    def _on_column_menu(self, cid):
        Toast.show(self._page, f"列操作: {cid}", "info")

    def _on_create_task(self, e):
        from app.ui.components.create_task_dialog import CreateTaskDialog
        CreateTaskDialog.open(self._page)

    def _on_settings_click(self, e):
        from app.ui.pages.settings_window import SettingsOverlay
        SettingsOverlay.open(self._page)

    def _on_filter_click(self, e):
        f = board_service.get_board().filters
        if f.is_active:
            board_service.set_filters(FilterState())
            Toast.show(self._page, "筛选已清除", "info")
        else:
            self._dlg_filter()

    # ── 内联搜索 ──

    def _on_search_focus(self):
        if self._search_box:
            self._search_box.border = ft.border.all(1, "#5294e2")
            self._search_box.update()

    def _on_search_blur(self):
        if self._search_box:
            self._search_box.border = ft.border.all(1, "#2a2a2a")
            self._search_box.update()

    def _on_search_clear(self, e):
        if self._search_field:
            self._search_field.value = ""
            self._search_field.update()
            board_service.set_filters(FilterState())
            if self._search_clear_btn:
                self._search_clear_btn.visible = False
                self._search_clear_btn.update()

    def _on_search_input(self, e):
        val = (e.control.value or "").strip()
        if self._search_clear_btn:
            self._search_clear_btn.visible = len(val) > 0
            self._search_clear_btn.update()
        if len(val) >= 1:
            board_service.set_filters(FilterState(search_query=val))
        else:
            board_service.set_filters(FilterState())

    def _on_search_submit(self, e):
        val = (e.control.value or "").strip()
        if val.startswith(">"):
            # AI query
            self._do_agent_query(val[1:].strip())
        elif val.startswith("/"):
            parts = val.split(maxsplit=1)
            self._do_command(parts[0].lower(), parts[1] if len(parts) > 1 else "")
        elif val:
            board_service.set_filters(FilterState(search_query=val))
            Toast.show(self._page, f"搜索: {val}", "info")

    # ── 命令面板 ──

    def _on_command_execute(self, action, value):
        if action == "create_task":
            from app.ui.components.create_task_dialog import CreateTaskDialog
            CreateTaskDialog.open(self._page)
        elif action == "generate_report": self._do_command("/report", "")
        elif action == "check_compliance": self._do_command("/compliance", "")
        elif action.startswith("filter_ata_"):
            ata = action.replace("filter_ata_", "")
            board_service.set_filters(FilterState(ata_chapters=[ata]))
            Toast.show(self._page, f"已筛选 ATA {ata}", "info")
        elif action == "nl_query":
            self._do_agent_query(value)
        else:
            Toast.show(self._page, f"操作: {action}", "info")

    def _do_command(self, cmd, arg):
        if cmd == "/report":
            try:
                from app.ui.services.agent_service import AgentService
                report = AgentService.get_daily_report()
                self._show_ai_in_panel("每日维护报告", report)
            except Exception as e:
                Toast.show(self._page, f"报告生成失败: {e}", "warning")
        elif cmd == "/compliance":
            self._show_ai_in_panel("合规检查", "正在检查 AD/SB 状态...")
        elif cmd == "/kb":
            try:
                from app.ui.services.agent_service import AgentService
                result = AgentService.search_knowledge(arg or "aviation maintenance")
                self._show_ai_in_panel(f"知识库: {arg}", result)
            except Exception as e:
                Toast.show(self._page, f"检索失败: {e}", "warning")
        else:
            Toast.show(self._page, f"未知命令: {cmd}", "warning")

    # ═══════════════════════════════════════════
    # AI 命令辅助 — 已迁移到 app/ui/services/ai_command_runner.py ──
    # ═══════════════════════════════════════════

    @property
    def _runner(self):
        """AI 命令执行器（懒初始化）。"""
        if not hasattr(self, '_runner_inst'):
            from app.ui.services.ai_command_runner import AICommandRunner
            self._runner_inst = AICommandRunner(self)
        return self._runner_inst

    def _run_agent_command(self, cmd: str):
        """AI 工具菜单命令分发。"""
        from app.ui.services.agent_service import AgentService

        if cmd == "outline":
            self._cmd_outline()
        elif cmd == "gen_tasks":
            self._cmd_gen_tasks()
        elif cmd == "classify":
            self._cmd_classify()
        elif cmd == "schedule":
            self._cmd_schedule()
        elif cmd == "acceptance":
            self._cmd_acceptance()
        elif cmd == "report":
            self._cmd_report()
        elif cmd == "review":
            self._cmd_review()
        else:
            Toast.show(self._page, f"未知 AI 命令: {cmd}", "warning")

    # ═══════════════════════════════════════════
    # 1. 生成大纲 → AI 面板交互
    # ═══════════════════════════════════════════

    def _cmd_outline(self):
        if not self._runner.ensure_ready(): return
        self._runner.setup("生成大纲", "outline")

        import threading, time

        def _do_outline():
            cancel = self._runner.get_cancel()
            try:
                from app.ui.services.agent_service import AgentService
                from app.agent.orchestrator import _load_prompt
                self.ai_chat.update_task_card("正在分析需求...")
                prompt = _load_prompt("generate_outline_interactive.md")
                result = AgentService.ask(
                    prompt, session_id="outline", strict=True,
                    cancel_event=cancel)
                if cancel and cancel.is_set():
                    self._finish_task_card("生成大纲", "已取消", theme.text_disabled)
                    return
                self.ai_chat.show_prompt_bubble(result)
                self.ai_chat.update_task_card("请回复上方紫色气泡中的问题...")
                busy_seen = False
                for _ in range(300):
                    if cancel and cancel.is_set():
                        self._finish_task_card("生成大纲", "已取消", theme.text_disabled)
                        return
                    time.sleep(1)
                    if not self.ai_chat: break
                    if self.ai_chat._busy:
                        busy_seen = True
                        self.ai_chat.update_task_card("正在生成大纲...", border_color=theme.warning)
                    elif busy_seen:
                        self.ai_chat.update_task_card("生成完成 — 点击「完成」关闭", border_color=theme.success)
                        self.ai_chat.mark_task_done()
                        self.ai_chat.show_status_bubble("生成大纲 完成", theme.success)
                        break
            except Exception as ex:
                self._finish_task_card("生成大纲", f"失败: {ex}", theme.error)

        threading.Thread(target=_do_outline, daemon=True).start()

    # ═══════════════════════════════════════════
    # 2. 生成任务 → AI 面板交互
    # ═══════════════════════════════════════════

    _CMD_PROMPTS = {
        "gen_tasks": (
            "根据当前看板上下文，为待处理的任务生成详细任务卡片。"
            "使用 create_task 工具为每个任务创建到待处理列。"
            "任务应包含标题、描述、ATA 章节、优先级和任务类型。"
        ),
        "classify": (
            "检查所有待处理（backlog）任务，根据航空维修优先级规则为每个任务分配优先级。"
            "使用 classify_task 工具将每个待处理任务移至已分类列。"
            "AOG > Cat A (当日) > Cat B (72h) > Cat C (10天) > Cat D (120天)。"
        ),
        "schedule": (
            "检查所有已分类（triage）任务，为每个任务排程。"
            "使用 search_employees 查找合适的员工，使用 schedule_task 工具排程。"
            "设置合理的计划开始/完成时间和工时。考虑员工技能和可用性。"
        ),
        "acceptance": (
            "以零容忍标准审核所有验收中（inspection）任务。默认判决：驳回。"
            "逐一检查：交接日志质量、字段完整性、合规性、安全性、检查清单、数据一致性。"
            "使用 get_task_detail 查看每个任务详情（尤其交接班日志内容），"
            "使用 search_knowledge_base 验证 ATA 标准合规性。"
            "对每个任务调用 acceptance_review 工具：recommendation=approve(零缺陷)或reject(有任何问题)。"
            "驳回理由必须具体——引用日志中的模糊用语、缺失的测量值、未签的 RII。"
            "必须对每个验收中任务调用一次 acceptance_review——不要写文字报告！"
        ),
    }

    def _cmd_gen_tasks(self):
        if not self._runner.ensure_ready(): return
        self._runner.setup("生成任务", "gen_tasks")

        import threading, time

        def _do_gen():
            import traceback
            cancel = self._runner.get_cancel() if self.ai_chat else None
            if cancel is None:
                self.ai_chat.hide_task_card() if self.ai_chat else None
                return
            try:
                from app.ui.services.agent_service import AgentService
                from app.agent.orchestrator import _load_prompt
                self.ai_chat.update_task_card("正在分析需求...")
                prompt = _load_prompt("generate_tasks_interactive.md")
                result = AgentService.ask(
                    prompt, session_id="gen_tasks", strict=True,
                    cancel_event=cancel)
                if cancel and cancel.is_set():
                    self._finish_task_card("生成任务", "已取消", theme.text_disabled)
                    return

                # 显示 Agent 提问为紫色需求气泡
                self.ai_chat.show_prompt_bubble(result)
                self.ai_chat.update_task_card("请回复上方紫色气泡中的问题...")
                known_before = {t.id for t in state.get_all_tasks()}
                busy_seen = False
                for _ in range(300):
                    if cancel and cancel.is_set():
                        self._finish_task_card("生成任务", "已取消", theme.text_disabled)
                        return
                    time.sleep(1)
                    if not self.ai_chat: break
                    if self.ai_chat._busy:
                        busy_seen = True
                        self.ai_chat.update_task_card("正在生成任务...", border_color=theme.warning)
                    elif busy_seen:
                        new_tasks = [t for t in state.get_all_tasks()
                                      if t.ai_proposed and t.id not in known_before]
                        if new_tasks:
                            self._refresh_board()
                            self._poll_ghost_resolution("生成任务", {t.id for t in new_tasks}, cancel)
                        break
            except Exception as ex:
                traceback.print_exc()
                try:
                    self._finish_task_card("生成任务", f"失败: {ex}", theme.error)
                except Exception:
                    self.ai_chat.hide_task_card() if self.ai_chat else None

        threading.Thread(target=_do_gen, daemon=True).start()

    # ═══════════════════════════════════════════
    # 3. 自动分类 → AI 面板交互
    # ═══════════════════════════════════════════

    def _cmd_classify(self):
        log.debug("classify", "_cmd_classify called")
        if not self.ai_chat:
            log.debug("CLASSIFY", "no ai_chat!")
            return
        if self.ai_chat.is_task_running:
            log.debug("CLASSIFY", "task already running")
            return
        backlog = [t for t in state.get_all_tasks() if t.status.value == "backlog"]
        log.debug("classify", f"backlog count={len(backlog)}")
        if not backlog:
            self._open_ai_panel()
            self._show_ai_in_panel("自动分类", "待处理列中没有任务需要分类。")
            return
        tasks_str = "\n".join(
            f"- [{t.id}] {t.title} (ATA {t.ata_chapter or '未指定'}, 飞机 {t.aircraft_reg or '未指定'})"
            for t in backlog
        )
        self._runner.setup("自动分类", "classify", initial_status=f"正在分析 {len(backlog)} 个任务...")
        self.ai_chat.update_task_card(f"正在分析 {len(backlog)} 个任务...")

        import threading, traceback

        def _do():
            log.debug("classify", "_do thread started")
            cancel = self._runner.get_cancel()
            log.debug("classify", f"cancel_event={cancel}")
            try:
                from app.ui.services.agent_service import AgentService
                prompt = (f"{self._CMD_PROMPTS['classify']}\n\n"
                          f"待处理任务:\n{tasks_str}\n\n使用 classify_task 逐个分类。")
                self.ai_chat.update_task_card("正在执行分类...", border_color=theme.warning)
                # 清除残留 ai_proposed，确保能检测到新幽灵卡
                for bt in backlog:
                    if bt.ai_proposed:
                        state.update_task(bt.id, ai_proposed=False, ai_priority=None)
                pending_before = {t.id for t in state.get_all_tasks() if t.ai_proposed}
                log.debug("classify", f"before ask, pending_before={len(pending_before)}")
                result = AgentService.ask(prompt, session_id="classify", cancel_event=cancel)
                log.debug("classify", f"ask done, result_len={len(result) if result else 0}")
                if cancel and cancel.is_set():
                    self._finish_task_card("自动分类", "已取消", theme.text_disabled)
                    return
                self._refresh_board()
                # 刷新对话面板提案 UI（幽灵卡在 refresh_board 中已渲染到看板）
                self._rebuild_chat_ui_sync()
                pending_after = {t.id for t in state.get_all_tasks() if t.ai_proposed}
                pending = pending_after - pending_before
                if pending:
                    self._poll_ghost_resolution("自动分类", pending, cancel)
                else:
                    self._finish_task_card("自动分类", "完成（无幽灵卡）", theme.success)
            except Exception as ex:
                self._finish_task_card("自动分类", f"失败: {ex}", theme.error)

        log.debug("classify", "starting thread")
        threading.Thread(target=_do, daemon=True).start()
        log.debug("classify", "thread started")

    # ═══════════════════════════════════════════
    # 4. 自动排程 → AI 面板交互
    # ═══════════════════════════════════════════

    def _cmd_schedule(self):
        if not self.ai_chat:
            Toast.show(self._page, "AI 面板未就绪", "warning"); return
        if self.ai_chat.is_task_running:
            Toast.show(self._page, "AI 正在处理中，请等待当前任务完成", "warning"); return
        triage = [t for t in state.get_all_tasks() if t.status.value == "triage"]
        if not triage:
            self._open_ai_panel()
            self._show_ai_in_panel("自动排程", "已分类列中没有任务需要排程。")
            return
        tasks_str = "\n".join(
            f"- [{t.id}] {t.title} (优先级: {t.priority.value}, ATA {t.ata_chapter or '未指定'})"
            for t in triage
        )
        self._runner.setup("自动排程", "schedule", initial_status=f"正在分析 {len(triage)} 个任务...")
        self.ai_chat.update_task_card(f"正在分析 {len(triage)} 个任务...")

        import threading
        def _do():
            cancel = self._runner.get_cancel()
            try:
                from app.ui.services.agent_service import AgentService
                prompt = (f"{self._CMD_PROMPTS['schedule']}\n\n"
                          f"已分类任务:\n{tasks_str}\n\n"
                          f"使用 search_employees + schedule_task 逐个排程。")
                self.ai_chat.update_task_card("正在执行排程...", border_color=theme.warning)
                # 清除残留 ai_proposed，确保能检测到新幽灵卡
                for tt in triage:
                    if tt.ai_proposed:
                        state.update_task(tt.id, ai_proposed=False)
                pending_before = {t.id for t in state.get_all_tasks() if t.ai_proposed}
                result = AgentService.ask(prompt, session_id="schedule", cancel_event=cancel)
                if cancel and cancel.is_set():
                    self._finish_task_card("自动排程", "已取消", theme.text_disabled)
                    return
                self._refresh_board()
                self._rebuild_chat_ui_sync()
                pending_after = {t.id for t in state.get_all_tasks() if t.ai_proposed}
                pending = pending_after - pending_before
                if pending:
                    self._poll_ghost_resolution("自动排程", pending, cancel)
                else:
                    self._finish_task_card("自动排程", "完成（无幽灵卡）", theme.success)
            except Exception as ex:
                self._finish_task_card("自动排程", f"失败: {ex}", theme.error)

        threading.Thread(target=_do, daemon=True).start()

    def _cmd_acceptance(self):
        log.debug("acceptance", "===== _cmd_acceptance called =====")
        if not self.ai_chat:
            log.debug("acceptance", "no ai_chat!")
            Toast.show(self._page, "AI 面板未就绪", "warning"); return
        if self.ai_chat.is_task_running:
            log.debug("acceptance", "task already running")
            Toast.show(self._page, "AI 正在处理中，请等待当前任务完成", "warning"); return
        insp = [t for t in state.get_all_tasks() if t.status.value == "inspection"]
        log.debug("acceptance", f"inspection tasks found: {len(insp)}")
        if not insp:
            self._open_ai_panel()
            self._show_ai_in_panel("自动验收", "验收列中没有任务。")
            return
        for t in insp:
            log.debug("acceptance", f"- {t.id}: {t.title} | log={'有' if t.shift_handover_log else '无'} | ai_proposed={t.ai_proposed} | rec={t.ai_acceptance_recommendation}")
        tasks_str = "\n".join(
            f"- [{t.id}] {t.title} (负责人: {t.employee_name or '未指定'})"
            for t in insp
        )
        self._runner.setup("自动验收", "acceptance", initial_status=f"正在审核 {len(insp)} 个任务...")
        self.ai_chat.update_task_card(f"正在审核 {len(insp)} 个任务...")

        import threading, traceback

        def _do():
            cancel = self._runner.get_cancel()
            log.debug("acceptance", f"_do thread started, cancel_event={cancel}")
            try:
                from app.ui.services.agent_service import AgentService
                prompt = (f"{self._CMD_PROMPTS['acceptance']}\n\n"
                          f"验收任务:\n{tasks_str}\n\n"
                          f"对每个验收中任务，必须调用 acceptance_review 工具提交审核建议。\n"
                          f"参数: task_id=任务ID, recommendation=approve(通过)或reject(驳回), reason=具体理由。\n"
                          f"不要只是写文字报告——必须调用工具！工具调用会创建幽灵卡片供人工确认。")
                log.debug("acceptance", f"prompt length={len(prompt)}")
                self.ai_chat.update_task_card("正在审核提交日志...", border_color=theme.warning)
                # 清除验收中任务残留的 ai_proposed 标记，确保本次能检测到新幽灵卡
                for t in insp:
                    if t.ai_proposed:
                        state.update_task(t.id, ai_proposed=False,
                                          ai_acceptance_recommendation=None,
                                          ai_acceptance_reason=None)
                        log.debug("acceptance", f"cleared stale ai_proposed for {t.id}")
                pending_before = {t.id for t in state.get_all_tasks() if t.ai_proposed}
                log.debug("acceptance", f"pending_before={len(pending_before)}: {pending_before}")
                log.debug("acceptance", f"calling AgentService.ask()...")
                result = AgentService.ask(prompt, session_id="acceptance", cancel_event=cancel)
                log.debug("acceptance", f"AgentService.ask() returned, len={len(result) if result else 0}")
                log.debug("acceptance", f"result[:300]={result[:300] if result else 'None'}")
                if cancel and cancel.is_set():
                    log.debug("acceptance", "cancelled after ask")
                    self._finish_task_card("自动验收", "已取消", theme.text_disabled)
                    return
                self._refresh_board()
                log.debug("acceptance", "_refresh_board() done")
                # 在聊天面板显示 Agent 审核报告
                self._show_ai_in_panel("自动验收", result)
                pending_after = {t.id for t in state.get_all_tasks() if t.ai_proposed}
                log.debug("acceptance", f"pending_after={len(pending_after)}: {pending_after}")
                pending = pending_after - pending_before
                log.debug("acceptance", f"new pending ghosts={len(pending)}: {pending}")
                if pending:
                    log.debug("acceptance", "entering _poll_ghost_resolution...")
                    self._poll_ghost_resolution("自动验收", pending, cancel)
                    log.debug("acceptance", "_poll_ghost_resolution returned")
                else:
                    log.debug("acceptance", "no pending ghosts, finishing")
                    self._finish_task_card("自动验收", "完成（无幽灵卡）", theme.success)
            except Exception as ex:
                traceback.print_exc()
                log.debug("acceptance", f"EXCEPTION: {ex}")
                self._finish_task_card("自动验收", f"失败: {ex}", theme.error)

        log.debug("acceptance", "starting thread")
        threading.Thread(target=_do, daemon=True).start()
        log.debug("acceptance", "thread started")

    # ═══════════════════════════════════════════
    # 6. 生成报表 → 弹窗显示 MD 报表、可保存
    # ═══════════════════════════════════════════

    def _cmd_report(self):
        """生成报表 — 可最小化后台运行。"""
        self._task_registry.register("report", "生成报表", "准备中...", "report", None)
        self._cmd_report_show_result(None)  # None = 加载中
        self._refresh_status_bar()

    def _cmd_report_show_result(self, content: str | None):
        """显示报表弹窗。content=None 表示加载中 / 已有缓存。"""
        ff = theme.font_family
        is_loading = content is None and self._report_result is None

        # ── body ──
        if is_loading:
            display = "正在生成报表..."
            progress = ft.ProgressRing(width=s(16), height=s(16), visible=True)
        elif content is not None:
            display = content
            progress = ft.ProgressRing(width=s(16), height=s(16), visible=False)
        else:
            display = self._report_result or ""
            progress = ft.ProgressRing(width=s(16), height=s(16), visible=False)

        report_f = ft.TextField(
            value=display, read_only=True, multiline=True,
            expand=True,
            border_color=theme.border,
            text_style=ft.TextStyle(color="#c0c0c0", size=s(11), font_family=ff),
            bgcolor=theme.card, border_radius=s(6),
        )

        # ── "_" 最小化按钮 ──
        def _minimize(e):
            dlg.close()
            # 不清除结果，状态栏保留入口

        # ── 取消任务 ──
        def _cancel(e):
            self._cancel_report()
            dlg.close()

        # ── header ──
        header = ft.Container(
            ft.Row([
                ft.Icon(ft.Icons.ASSESSMENT_OUTLINED, size=s(15), color="#5294e2"),
                ft.Text("生成维护报表", size=s(14), weight=ft.FontWeight.W_600,
                        color=theme.text_primary, font_family=ff),
                progress,
                ft.Container(expand=True),
                ft.IconButton(ft.Icons.MINIMIZE_OUTLINED, icon_size=s(15),
                              icon_color=theme.text_secondary,
                              tooltip="最小化后台运行",
                              style=ft.ButtonStyle(
                                  bgcolor=ft.Colors.TRANSPARENT,
                                  overlay_color="#1a1a1a",
                                  shape=ft.RoundedRectangleBorder(radius=s(4))),
                              on_click=lambda e: _minimize(e)),
            ], spacing=s(8)),
            padding=ft.padding.only(left=s(14), top=s(8), right=s(6), bottom=s(8)),
            border=ft.border.only(bottom=ft.BorderSide(1, theme.border)),
        )

        # ── footer ──
        btn_st = ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=s(6)),
            padding=ft.padding.only(left=s(18), top=s(7), right=s(18), bottom=s(7)),
            text_style=ft.TextStyle(size=s(12), font_family=ff),
        )

        def _save(e):
            import os
            os.makedirs("data/reports", exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = f"data/reports/report_{ts}.md"
            with open(path, "w", encoding="utf-8") as f:
                f.write(report_f.value or "")
            Toast.show(self._page, f"已保存: {path}", "success")
            self._report_result = report_f.value
            _minimize(e)

        if is_loading:
            footer_btns = [
                ft.OutlinedButton("取消任务", on_click=_cancel,
                    style=ft.ButtonStyle(
                        shape=btn_st.shape, padding=btn_st.padding,
                        text_style=btn_st.text_style,
                        side=ft.BorderSide(1, theme.error),
                        color=theme.error)),
                ft.Container(expand=True),
                ft.OutlinedButton("最小化运行", on_click=_minimize,
                    style=ft.ButtonStyle(
                        shape=btn_st.shape, padding=btn_st.padding,
                        text_style=btn_st.text_style,
                        side=ft.BorderSide(1, theme.border),
                        color=theme.text_secondary)),
                ft.ElevatedButton("保存报表", on_click=_save,
                    style=ft.ButtonStyle(
                        shape=btn_st.shape, padding=btn_st.padding,
                        text_style=btn_st.text_style,
                        bgcolor="#5294e2", color=ft.Colors.WHITE, elevation=0)),
            ]
        else:
            footer_btns = [
                ft.Container(expand=True),
                ft.ElevatedButton("保存报表", on_click=_save,
                    style=ft.ButtonStyle(
                        shape=btn_st.shape, padding=btn_st.padding,
                        text_style=btn_st.text_style,
                        bgcolor="#5294e2", color=ft.Colors.WHITE, elevation=0)),
            ]

        footer = ft.Container(
            ft.Row(footer_btns, spacing=s(8)),
            padding=ft.padding.only(left=s(14), top=s(8), right=s(14), bottom=s(10)),
            border=ft.border.only(top=ft.BorderSide(1, theme.border)),
        )

        PW, PH = 720, 780
        page_w = self._page.width or 1280
        page_h = self._page.height or 900
        cx = max(0, (page_w - PW) // 2)
        cy = max(20, (page_h - PH) // 2)

        panel = ft.Container(
            content=ft.Column([
                header,
                ft.Container(report_f, padding=ft.padding.all(s(14)), expand=True),
                footer,
            ], spacing=0, expand=True, tight=True),
            width=PW, height=PH, bgcolor=theme.surface, border_radius=s(10),
            border=ft.border.all(1, theme.border),
            shadow=ft.BoxShadow(spread_radius=1, blur_radius=20, color="#000000aa"),
            left=cx, top=cy,
        )

        from app.ui.widgets.overlay_dimmer import OverlayDimmer
        dlg = OverlayDimmer.open(self._page, panel, dim_opacity=0.55)
        self._report_dlg = dlg

        # ── 异步生成（仅加载中且无运行中线程时）──
        if is_loading and (self._report_thread is None or not self._report_thread.is_alive()):
            import threading
            def _gen():
                try:
                    from app.ui.services.agent_service import AgentService
                    r = AgentService.generate_report("daily")
                    report_f.value = r
                    self._report_result = r
                    self._task_registry.update_status("report", "已完成", 1.0)
                except Exception as ex:
                    report_f.value = f"生成失败: {ex}"
                    self._report_result = f"生成失败: {ex}"
                    self._task_registry.update_status("report", "失败", 0)
                progress.visible = False
                try: progress.update(); report_f.update()
                except Exception: pass
                # 5 秒后自动消失
                import time; time.sleep(5)
                self._task_registry.unregister("report")
            t = threading.Thread(target=_gen, daemon=True)
            self._report_thread = t
            t.start()

    # ═══════════════════════════════════════════
    # 7. 任务审核 → 弹窗显示合规问题
    # ═══════════════════════════════════════════

    def _cmd_review(self):
        """任务审核 — 可最小化后台运行。"""
        self._task_registry.register("review", "任务审核", "准备中...", "review", None)
        self._cmd_review_show_result(None)
        self._refresh_status_bar()

    def _cmd_review_show_result(self, cached_result: dict | None):
        """显示审核弹窗。cached_result=None 表示加载中。"""
        ff = theme.font_family
        result = cached_result or self._review_result
        is_loading = result is None
        log.debug("review", f"===== _cmd_review_show_result loading={is_loading} =====")

        # ── 关闭旧弹窗避免叠加 ──
        if self._review_dlg:
            try: self._review_dlg.close()
            except Exception: pass
            self._review_dlg = None

        # ── body：审核结果列表 ──
        issue_list = ft.ListView(spacing=s(8), expand=True,
                                 padding=ft.padding.all(s(14)))
        self._review_issue_list = issue_list  # 存储引用供批量更新

        if is_loading:
            issue_list.controls.append(
                ft.Container(
                    ft.Column([
                        ft.ProgressRing(width=s(24), height=s(24)),
                        ft.Text("正在审核任务合规性...", size=s(13),
                                color=theme.text_primary, font_family=ff),
                        ft.Text("检查 ATA 章节、飞机注册号、RII 合规、排程可行性...",
                                size=s(11), color=theme.text_secondary, font_family=ff),
                    ], spacing=s(12), alignment=ft.MainAxisAlignment.CENTER,
                       horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=ft.padding.symmetric(vertical=s(50)),
                    alignment=ft.alignment.center,
                ))
        else:
            # 有缓存结果 → 直接渲染 issue 卡片
            self._render_issue_cards(issue_list,
                result.get("issues", []), ff)

        # ── 最小化 / 取消 ──
        def _minimize_review(d):
            d.close()
        def _cancel_review_task(d):
            self._cancel_review()
            d.close()

        # ── header（单行 + 统计 badges，存储引用供批量更新）──
        if is_loading:
            review_summary_container = ft.Container(visible=False)
        else:
            review_summary_container = ft.Container(
                content=ft.Row(self._build_review_summary(result, ff), spacing=s(12)))
        self._review_summary_container = review_summary_container

        header = ft.Container(
            ft.Row([
                ft.Icon(ft.Icons.FACT_CHECK_OUTLINED, size=s(15), color="#5294e2"),
                ft.Text("任务合规审核", size=s(14), weight=ft.FontWeight.W_600,
                        color=theme.text_primary, font_family=ff),
                review_summary_container,
                ft.Container(expand=True),
                ft.IconButton(ft.Icons.MINIMIZE_OUTLINED, icon_size=s(15),
                              icon_color=theme.text_secondary,
                              tooltip="最小化后台运行",
                              style=ft.ButtonStyle(
                                  bgcolor=ft.Colors.TRANSPARENT,
                                  overlay_color="#1a1a1a",
                                  shape=ft.RoundedRectangleBorder(radius=s(4))),
                              on_click=lambda e: _minimize_review(dlg)),
            ], spacing=s(8)),
            padding=ft.padding.only(left=s(14), top=s(8), right=s(6), bottom=s(8)),
            border=ft.border.only(bottom=ft.BorderSide(1, theme.border)),
        )

        # ── footer ──
        btn_st = ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=s(6)),
            padding=ft.padding.only(left=s(18), top=s(7), right=s(18), bottom=s(7)),
            text_style=ft.TextStyle(size=s(12), font_family=ff),
        )
        if is_loading:
            footer_btns = [
                ft.OutlinedButton("取消任务", on_click=lambda e: _cancel_review_task(dlg),
                    style=ft.ButtonStyle(
                        shape=btn_st.shape, padding=btn_st.padding,
                        text_style=btn_st.text_style,
                        side=ft.BorderSide(1, theme.error),
                        color=theme.error)),
                ft.Container(expand=True),
                ft.OutlinedButton("最小化运行", on_click=lambda e: _minimize_review(dlg),
                    style=ft.ButtonStyle(
                        shape=btn_st.shape, padding=btn_st.padding,
                        text_style=btn_st.text_style,
                        side=ft.BorderSide(1, theme.border),
                        color=theme.text_secondary)),
            ]
        else:
            def _save_json(e):
                import os, json
                os.makedirs("data/reports", exist_ok=True)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                path = f"data/reports/review_{ts}.json"
                data = self._review_result or {}
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                Toast.show(self._page, f"已保存: {path}", "success")
            footer_btns = [
                ft.Container(expand=True),
                ft.OutlinedButton("最小化运行", on_click=lambda e: _minimize_review(dlg),
                    style=ft.ButtonStyle(
                        shape=btn_st.shape, padding=btn_st.padding,
                        text_style=btn_st.text_style,
                        side=ft.BorderSide(1, theme.border),
                        color=theme.text_secondary)),
                ft.ElevatedButton("保存结果", on_click=_save_json,
                    style=ft.ButtonStyle(
                        shape=btn_st.shape, padding=btn_st.padding,
                        text_style=btn_st.text_style,
                        bgcolor="#5294e2", color=ft.Colors.WHITE, elevation=0)),
            ]
        footer = ft.Container(
            ft.Row(footer_btns, spacing=s(8)),
            padding=ft.padding.only(left=s(14), top=s(8), right=s(14), bottom=s(10)),
            border=ft.border.only(top=ft.BorderSide(1, theme.border)),
        )

        PW, PH = 720, 780
        page_w = self._page.width or 1280
        page_h = self._page.height or 900
        cx = max(0, (page_w - PW) // 2)
        cy = max(20, (page_h - PH) // 2)

        panel = ft.Container(
            content=ft.Column([
                header,
                issue_list,
                footer,
            ], spacing=0, expand=True, tight=True),
            width=PW, height=PH, bgcolor=theme.surface, border_radius=s(10),
            border=ft.border.all(1, theme.border),
            shadow=ft.BoxShadow(spread_radius=1, blur_radius=20, color="#000000aa"),
            left=cx, top=cy,
        )

        from app.ui.widgets.overlay_dimmer import OverlayDimmer
        dlg = OverlayDimmer.open(self._page, panel, dim_opacity=0.55)
        self._review_dlg = dlg

        # ── 异步审核 → Agent 深度分析 + 本地规则兜底 ──
        def _loading(msg):
            return ft.Container(
                ft.Column([
                    ft.ProgressRing(width=s(24), height=s(24)),
                    ft.Text(msg, size=s(13), color=theme.text_primary, font_family=ff),
                    ft.Text("Agent 正在分析任务数据、检索知识库标准...",
                            size=s(11), color=theme.text_secondary, font_family=ff),
                ], spacing=s(12), alignment=ft.MainAxisAlignment.CENTER,
                   horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.padding.symmetric(vertical=s(50)),
                alignment=ft.alignment.center)

        import threading
        def _review():
            log.debug("review", "_review thread started")
            try:
                from app.ui.services.agent_service import AgentService

                # 渐进回调：每批完成后原地更新弹窗控件（不关闭重开）
                def _on_batch(issues_so_far, batch_num=0, total_batches=0):
                    reviewed = batch_num * 6 if batch_num else 0
                    batch_result = {
                        "issues": issues_so_far,
                        "total_issues": len(issues_so_far),
                        "critical_count": sum(1 for i in issues_so_far if i.get("severity") == "critical"),
                        "warning_count": sum(1 for i in issues_so_far if i.get("severity") == "warning"),
                        "info_count": sum(1 for i in issues_so_far if i.get("severity") == "info"),
                        "tasks_reviewed": reviewed,
                    }
                    self._review_result = batch_result
                    # 原地更新 header 统计
                    if self._review_summary_container:
                        self._review_summary_container.content = ft.Row(
                            self._build_review_summary(batch_result, theme.font_family), spacing=s(12))
                        self._review_summary_container.visible = True
                        try: self._review_summary_container.update()
                        except Exception: pass
                    # 原地重建 issue 列表
                    if self._review_issue_list:
                        self._review_issue_list.controls.clear()
                        self._render_issue_cards(self._review_issue_list, issues_so_far, theme.font_family)
                        try: self._review_issue_list.update()
                        except Exception: pass
                    # 更新状态栏
                    self._task_registry.update_status("review", f"审核中 ({len(issues_so_far)}个问题)", 0.5)
                    log.debug("review", f"batch rendered in-place: {len(issues_so_far)} issues so far")

                log.debug("review", "calling AgentService.task_review() with batching...")
                result = AgentService.task_review(on_batch=_on_batch)
                log.debug("review", f"task_review done: issues={result.get('total_issues',0)}")
            except Exception as ex:
                import traceback; traceback.print_exc()
                result = {"issues": [{
                    "task_id": "", "title": "Agent 审核失败", "severity": "critical",
                    "dimension": "系统错误",
                    "description": "Agent 未正常返回审核结果。",
                    "recommendation": f"错误: {str(ex)[:200]}",
                }], "total_issues": 1, "critical_count": 1,
                    "warning_count": 0, "info_count": 0, "tasks_reviewed": 0}

            # 存储最终结果，触发重渲染
            self._review_result = result
            self._task_registry.update_status("review", "已完成", 1.0)
            if self._review_dlg:
                self._cmd_review_show_result(result)
            import time; time.sleep(5)
            self._task_registry.unregister("review")

        # 仅加载中且无运行中线程时才启动
        if is_loading and (self._review_thread is None or not self._review_thread.is_alive()):
            log.debug("review", "starting review thread")
            t = threading.Thread(target=_review, daemon=True)
            self._review_thread = t
            t.start()
            log.debug("review", "review thread started")
        else:
            log.debug("review", "review already running or result cached, skipping thread")

    # ── 审核结果渲染辅助 ──

    @staticmethod
    def _build_review_summary(result: dict, ff: str) -> list:
        """构建审核汇总 badges。"""
        total = result.get("total_issues", 0)
        tasks_r = result.get("tasks_reviewed", 0)
        sc = [ft.Text(f"审核 {tasks_r} 个任务", size=s(11),
                      color=theme.text_secondary, font_family=ff)]
        if total == 0:
            sc.append(ft.Container(
                ft.Text("✅ 全部合规", size=s(11), color=theme.success,
                        weight=ft.FontWeight.W_600, font_family=ff),
                padding=ft.padding.only(left=s(8), top=s(2), right=s(8), bottom=s(2)),
                border_radius=s(4),
                bgcolor=ft.Colors.with_opacity(0.12, theme.success)))
        else:
            for key, label, color in [("critical_count", "🔴", theme.error),
                                       ("warning_count", "⚠", theme.warning),
                                       ("info_count", "ℹ", theme.info)]:
                n = result.get(key, 0)
                if n:
                    sc.append(ft.Container(
                        ft.Text(f"{label} {n}", size=s(10), color=color,
                                weight=ft.FontWeight.W_600, font_family=ff),
                        padding=ft.padding.only(left=s(6), top=s(1), right=s(6), bottom=s(1)),
                        border_radius=s(3),
                        bgcolor=ft.Colors.with_opacity(0.10, color)))
        return sc

    def _render_issue_cards(self, issue_list: ft.ListView, issues: list, ff: str):
        """渲染问题卡片到 ListView。"""
        sev_colors = {"critical": theme.error, "warning": theme.warning, "info": theme.info}
        sev_labels = {"critical": "严重", "warning": "警告", "info": "提示"}
        sev_icons = {"critical": ft.Icons.ERROR_OUTLINE,
                     "warning": ft.Icons.WARNING_AMBER_OUTLINED,
                     "info": ft.Icons.INFO_OUTLINE}

        for issue in issues:
            sev = issue.get("severity", "info")
            accent = sev_colors.get(sev, theme.info)
            tid = issue.get("task_id", "")
            title = issue.get("title", "")
            dimension = issue.get("dimension", "")
            description = issue.get("description", "")
            recommendation = issue.get("recommendation", "")

            def _nav_to(t, d):
                return lambda e: self._navigate_to_issue(t, d)

            card = ft.Container(
                ft.Row([
                    ft.Container(width=s(3), border_radius=s(2), bgcolor=accent),
                    ft.Column([
                        ft.Row([
                            ft.Container(
                                ft.Row([
                                    ft.Icon(sev_icons.get(sev, ft.Icons.INFO_OUTLINE),
                                            size=s(10), color=accent),
                                    ft.Text(sev_labels.get(sev, sev), size=s(9),
                                            color=accent, weight=ft.FontWeight.W_600,
                                            font_family=ff),
                                ], spacing=s(3)),
                                padding=ft.padding.only(left=s(5), top=s(1),
                                                       right=s(5), bottom=s(1)),
                                border_radius=s(3),
                                bgcolor=ft.Colors.with_opacity(0.10, accent)),
                            ft.Text(dimension, size=s(10),
                                    color=theme.text_disabled, font_family=ff),
                        ], spacing=s(6)),
                        ft.Container(height=s(4)),
                        ft.Text(title, size=s(12), weight=ft.FontWeight.W_500,
                                color=theme.text_primary, font_family=ff),
                        ft.Container(height=s(2)),
                        ft.Text(description, size=s(11),
                                color=theme.text_primary, font_family=ff),
                        ft.Text(recommendation, size=s(10),
                                color=theme.text_secondary, font_family=ff, italic=True),
                        ft.Container(height=s(4)),
                        ft.Row([
                            ft.Container(expand=True),
                            ft.TextButton(
                                content=ft.Text("查看任务 →", size=s(11),
                                                color=theme.info, font_family=ff),
                                style=ft.ButtonStyle(bgcolor=ft.Colors.TRANSPARENT,
                                    padding=ft.padding.symmetric(horizontal=s(8), vertical=s(2))),
                                on_click=_nav_to(tid, self._review_dlg)),
                        ]),
                    ], spacing=0, tight=True, expand=True),
                ], spacing=s(10), vertical_alignment=ft.CrossAxisAlignment.START),
                padding=ft.padding.all(s(10)),
                border_radius=s(8),
                bgcolor=ft.Colors.with_opacity(0.04, accent),
                border=ft.border.only(left=ft.BorderSide(s(3), accent)),
            )
            issue_list.controls.append(card)

    def _navigate_to_issue(self, task_id: str, dlg=None):
        """从审核弹窗跳转到任务卡片：关闭弹窗，清筛选，打开侧边栏。"""
        if dlg:
            try:
                dlg.close()
            except Exception:
                pass

        t = state.get_task(task_id)
        if not t:
            Toast.show(self._page, f"任务 {task_id} 不存在", "warning")
            return

        # 清除筛选确保任务可见
        from app.core.services.board_service import board_service
        board_service.set_filters(FilterState())
        self._refresh_board()

        # 打开侧边栏显示任务详情
        if self.side_panel:
            if self.ai_chat and self.ai_chat.is_open:
                self.ai_chat.close()
            self.side_panel.open_task(t)

        self._page.update()

    async def _rebuild_chat_ui(self):
        """主线程调度：重建 AI 对话气泡 + 提案 UI（用于 run_task）。"""
        self._rebuild_chat_ui_sync()

    def _rebuild_chat_ui_sync(self):
        """同步版本：后台线程直接调用（项目现有模式）。"""
        try:
            if self.ai_chat:
                self.ai_chat._rebuild_bubbles()
                self.ai_chat.update()
        except Exception:
            pass

    def _show_ai_in_panel(self, title: str, content: str):
        """在 AI 对话面板中显示结果。有脆弱内容时不重建。"""
        if not self.ai_chat or not self.ai_chat.is_open:
            self._open_ai_panel()
        try:
            if hasattr(self.ai_chat, '_msg_pairs'):
                from datetime import datetime
                self.ai_chat._msg_pairs.append((
                    f"[{title}]", content, datetime.now()))
                self.ai_chat._rebuild_bubbles()
                self.ai_chat.update()
        except Exception:
            pass

    def _do_agent_query(self, question):
        if not question:
            Toast.show(self._page, "请输入问题", "warning"); return
        try:
            from app.ui.services.agent_service import AgentService
            result = AgentService.ask(question)
            self._show_ai_in_panel(f"AI: {question[:50]}", result)
        except Exception as e:
            Toast.show(self._page, f"AI 未就绪: {e}", "warning")

    def _card_action(self, tid, action):
        """右键菜单动作分发。"""
        log.debug("card_action", f"tid={tid[:8]} action={action}")
        t = state.get_task(tid)
        if not t:
            log.debug("card_action", f"TASK NOT FOUND tid={tid}")
            return
        log.debug("card_action", f"task={t.title[:20]} col={t.status.value}")

        # ── 编辑 → 直接打开编辑弹窗 ──
        if action == "edit":
            self._dlg_edit(t)

        elif action == "delete":
            task_service.delete_task(tid)
            if self.side_panel: self.side_panel.close()
            Toast.show(self._page, "已删除", "info")

        elif action == "search":
            from app.ui.services.agent_service import AgentService
            task_info = {
                "id": tid, "title": t.title, "ata_chapter": t.ata_chapter,
                "aircraft_reg": t.aircraft_reg, "aircraft_model": t.aircraft_model or "",
                "fault_code": getattr(t, 'fault_code', '') or "",
            }
            self._run_ai_action("AI 查找文档", task_info,
                                lambda ci, ce: AgentService.search_docs(ci, ce),
                                f"search_{tid}")

        elif action == "ai_explain":
            from app.ui.services.agent_service import AgentService
            task_info = {
                "id": tid, "title": t.title, "description": t.description or "",
                "aircraft_reg": t.aircraft_reg, "aircraft_model": t.aircraft_model or "",
                "ata_chapter": t.ata_chapter, "task_type": t.task_type.value,
                "priority": t.priority.value, "zone": t.zone or "",
                "work_order_id": t.work_order_id, "estimated_hours": t.estimated_hours,
                "is_rii": t.is_rii,
            }
            self._run_ai_action("AI 解释任务", task_info,
                                lambda ci, ce: AgentService.explain_task(ci, ce),
                                f"explain_{tid}")

        elif action == "submit":
            self._dlg_submit(tid)

        elif action == "ai_review":
            self._cmd_acceptance()

        elif action == "ai_classify":
            from app.ui.services.agent_service import AgentService
            self._run_ai_action("AI 分类此任务", {
                "id": tid, "title": t.title, "description": t.description or "",
                "aircraft_reg": t.aircraft_reg, "ata_chapter": t.ata_chapter,
                "task_type": t.task_type.value, "aircraft_model": t.aircraft_model or "",
            }, lambda ci, ce: AgentService.classify_single(ci, ce),
            f"classify_{tid}", keep_open=True)

        elif action == "ai_schedule":
            from app.ui.services.agent_service import AgentService
            self._run_ai_action("AI 排程此任务", {
                "id": tid, "title": t.title, "description": t.description or "",
                "aircraft_reg": t.aircraft_reg, "ata_chapter": t.ata_chapter,
                "task_type": t.task_type.value, "priority": t.priority.value,
                "zone": t.zone or "", "estimated_hours": t.estimated_hours,
            }, lambda ci, ce: AgentService.schedule_single(ci, ce),
            f"schedule_{tid}", keep_open=True)

        elif action == "ai_review_single":
            from app.ui.services.agent_service import AgentService
            self._run_ai_action("AI 验收此任务", {
                "id": tid, "title": t.title, "description": t.description or "",
                "aircraft_reg": t.aircraft_reg, "aircraft_model": t.aircraft_model or "",
                "ata_chapter": t.ata_chapter, "task_type": t.task_type.value,
                "priority": t.priority.value, "zone": t.zone or "",
                "employee_name": t.employee_name or "", "employee_id": t.employee_id or "",
                "estimated_hours": t.estimated_hours, "actual_hours": t.actual_hours,
                "shift_handover_log": t.shift_handover_log or "(无)",
                "is_rii": t.is_rii, "checklist_progress": t.checklist_progress(),
            }, lambda ci, ce: AgentService.review_single(ci, ce),
            f"review_{tid}", keep_open=True)

        # ── 列移动（move_to:<target_col>） ──
        elif action.startswith("move_to:"):
            target_col = action.split(":", 1)[1]
            try:
                task_service.move_task(tid, target_col, changed_by="user")
                col_titles = {
                    "ready": "已标记就绪", "in_progress": "已开始执行",
                    "scheduled": "已退回已排程", "triage": "已退回已分类",
                    "backlog": "已退回待处理", "archived": "已归档",
                    "completed": "已完成",
                }
                msg = col_titles.get(target_col, f"已移至{target_col}")
                Toast.show(self._page, msg, "success")
            except Exception as e:
                Toast.show(self._page, str(e), "warning")

        # ── 阻塞 ──
        elif action == "block":
            self._dlg_block(tid)

        # ── 取消阻塞 ──
        elif action == "unblock":
            try:
                task_service.unblock_task(tid, "user")
                Toast.show(self._page, "已取消阻塞，任务返回就绪", "success")
            except Exception as e:
                Toast.show(self._page, str(e), "warning")

        # ── 设置优先级并分类（backlog → triage）—— 复用拖放弹窗 ──
        elif action == "set_priority":
            self._dlg_priority(tid, "triage", -1)

        # ── 更改优先级（triage，不移动）—— 复用同一弹窗 ──
        elif action == "change_priority":
            self._dlg_priority(tid)  # col=None → 仅更新优先级

        # ── 排程（triage → scheduled）—— 复用拖放弹窗 ──
        elif action == "schedule":
            self._dlg_schedule(tid, "scheduled", -1)

        # ── 重新排程（ready，不移动列）—— 复用排程弹窗 ──
        elif action == "reschedule":
            self._dlg_schedule(tid, move_to=False)

        # ── 直接归档（backlog → archived） ──
        elif action == "archive_now":
            try:
                task_service.move_task(tid, "archived", changed_by="user")
                Toast.show(self._page, "已归档", "success")
            except Exception as e:
                Toast.show(self._page, str(e), "warning")

        # ── 直接完成（in_progress → completed） ──
        elif action == "complete_direct":
            try:
                task_service.move_task(tid, "completed", changed_by="user")
                Toast.show(self._page, "已完成", "success")
            except Exception as e:
                Toast.show(self._page, str(e), "warning")

        # ── 验收通过（inspection → completed） ──
        elif action == "approve":
            try:
                task_service.move_task(tid, "completed", changed_by="user")
                Toast.show(self._page, "验收通过，已移至已完成", "success")
            except Exception as e:
                Toast.show(self._page, str(e), "warning")

    def _start_ghost_polling(self, session_id: str, label: str):
        """定期检查幽灵卡片是否已全部处理，若是则完成任务卡片。"""
        import threading, time
        def _poll():
            for _ in range(30):  # 最多轮询 60 秒
                time.sleep(2)
                # 检查是否已取消或已完成
                found = False
                for t in self._task_registry.get_all():
                    if t["id"] == session_id:
                        found = True
                        if t.get("status") not in ("等待确认",):
                            return  # 已被取消或完成
                        break
                if not found:
                    return  # 任务已被移除
                # 检查幽灵卡片
                proposed = [t for t in state.get_all_tasks() if t.ai_proposed]
                if not proposed:
                    log.debug("ghost_poll", f"all ghosts resolved, completing {session_id}")
                    self._check_ghost_pending_completion()
                    return
        threading.Thread(target=_poll, daemon=True).start()

    def _run_ai_action(self, label: str, task_info: dict,
                       action_fn, session_id: str, keep_open: bool = False):
        """通用 AI 动作：打开面板 + 任务卡片 + 后台调用 service 方法 + 结果气泡。"""
        log.debug("ai_action", f"_run_ai_action label={label} session={session_id} "
              f"ai_chat={'OK' if self.ai_chat else 'NONE'} "
              f"is_task_running={self.ai_chat.is_task_running if self.ai_chat else 'N/A'}")
        if not self.ai_chat:
            Toast.show(self._page, "AI 面板未就绪", "warning"); return
        if self.ai_chat.is_task_running:
            Toast.show(self._page, "AI 正在处理中，请等待当前任务完成", "warning"); return

        self._runner.setup(label, session_id)
        log.debug("ai_action", f"task registered, starting background thread...")

        import threading, traceback as _tb

        def _do():
            log.debug("ai_action_bg", f"thread started for {label}")
            cancel = self._runner.get_cancel()
            log.debug("ai_action_bg", f"cancel_event={'OK' if cancel else 'None'}")
            # 调用前检查取消（状态栏已处理清理，此处仅收尾 UI）
            if cancel and cancel.is_set():
                log.debug("ai_action_bg", f"pre-cancelled")
                self._finish_task_card(label, "已取消", theme.text_disabled)
                return
            try:
                self.ai_chat.update_task_card("正在分析...", border_color=theme.warning)
                log.debug("ai_action_bg", f"calling action_fn...")
                result = action_fn(task_info, cancel)
                log.debug("ai_action_bg", f"result len={len(result) if result else 0} "
                      f"preview={(result or '')[:100]}")
                if not result:
                    log.debug("ai_action_bg", f"empty result")
                    self._finish_task_card(label, "无结果", theme.error)
                    return
                if result.startswith("[Error]") or result == "回答已中断":
                    log.debug("ai_action_bg", f"error/cancelled: {result}")
                    self._finish_task_card(label, "已取消", theme.text_disabled)
                    return
                # 成功——通过 _msg_pairs + _rebuild_bubbles 保持响应式布局
                # __AI_ONLY__ 前缀：只显示 AI 气泡，不显示用户气泡
                log.debug("ai_action_bg", f"success, adding to _msg_pairs...")
                from datetime import datetime
                self.ai_chat._msg_pairs.append(
                    (f"__AI_ONLY__{label}", result, datetime.now()))
                try:
                    # 必须通过 page.run_task 调度到主线程更新 UI
                    if self._page:
                        self._page.run_task(self._rebuild_chat_ui)
                except Exception:
                    pass
                # 收尾
                if keep_open:
                    active_task_registry.clear()
                    # 检查 LLM 是否实际调用了工具（创建了幽灵卡片）
                    proposed = [t for t in state.get_all_tasks() if t.ai_proposed]
                    tid = task_info.get("id", "")
                    has_ghost = any(t.id == tid and t.ai_proposed for t in proposed)
                    if has_ghost:
                        self.ai_chat.update_task_card("等待确认幽灵卡片…", border_color=theme.warning)
                        self._task_registry.update_status(session_id, "等待确认", 0.8)
                        self._check_ghost_pending_completion()
                        self._start_ghost_polling(session_id, label)
                    else:
                        # AI 未调工具——当作失败处理
                        log.debug("ai_action_bg", f"keep_open but no ghost card created for {tid}")
                        self._finish_task_card(label, "AI 未创建提案", theme.error)
                else:
                    self._finish_task_card(label, "完成", theme.success)
                log.debug("ai_action_bg", f"done")
            except Exception as ex:
                log.debug("ai_action_bg", f"EXCEPTION: {ex}")
                _tb.print_exc()
                self._finish_task_card(label, f"失败: {ex}", theme.error)

        threading.Thread(target=_do, daemon=True).start()
        log.debug("ai_action", f"thread started")

    def handle_keyboard(self, e: ft.KeyboardEvent, page: ft.Page):
        # 幽灵文本键盘处理（Tab/Esc）—— 不影响 Ctrl+K 等组合键
        from app.ui.widgets.ghost_text import handle_ghost_keyboard
        if handle_ghost_keyboard(e):
            return

        k = e.key.lower()
        ctrl = e.ctrl or e.meta
        if ctrl and k == "k":
            if self.command_bar: self.command_bar.show(page)
            e.handled = True
        elif k == "escape":
            from app.ui.widgets.context_menu import close_current_menu
            close_current_menu()
            if self.side_panel and self.side_panel.is_open:
                self.side_panel.close(); self._refresh_board()
            e.handled = True

    # ═══════════════════════ 对话框 ═══════════════════════

    def _dlg_submit(self, tid):
        """提交任务结果弹窗 → 进入验收队列。"""
        t = state.get_task(tid)
        if not t: return
        ff = theme.font_family
        result_f = ft.TextField(
            label="交接班日志", hint_text="描述完成情况、发现的问题、遗留事项...",
            multiline=True, min_lines=4, max_lines=8,
            border_color=theme.border, focused_border_color=theme.info,
            text_style=ft.TextStyle(color=theme.text_primary, size=theme.font_md, font_family=ff),
            bgcolor=theme.card,
        )
        hours_f = ft.TextField(
            label="实际工时 (h)", hint_text="如 3.5", width=150,
            border_color=theme.border, focused_border_color=theme.info,
            text_style=ft.TextStyle(color=theme.text_primary, size=theme.font_md, font_family=ff),
            bgcolor=theme.card,
        )
        # 预填已有日志（如有）
        if t.shift_handover_log:
            result_f.value = t.shift_handover_log
        if t.actual_hours:
            hours_f.value = str(t.actual_hours)

        def submit(_):
            result = (result_f.value or "").strip()
            if not result:
                Toast.show(self._page, "请填写交接班日志", "warning"); return
            try:
                actual_hours = float(hours_f.value or "0")
            except ValueError:
                actual_hours = 0
            try:
                task_service.update_task(tid, shift_handover_log=result,
                                         actual_hours=actual_hours)
                task_service.move_task(tid, "inspection", changed_by="user")
                dlg.close()
                from app.core.models.log_entry import LogType
                from app.core.services.log_service import log_service
                log_service.log(LogType.SUBMISSION, task_id=tid,
                                task_title=t.title, user="user",
                                description=f"提交验收: {result[:60]}...")
                Toast.show(self._page, "已提交验收，等待审核", "success")
            except Exception as e:
                Toast.show(self._page, str(e), "warning")

        # ── 按钮 + 字段样式（与 CreateTaskDialog 一致）──
        field_style = ft.TextStyle(color="#e0e0e0", size=s(12), font_family=ff)
        hint_style = ft.TextStyle(color=theme.text_secondary, size=s(11), font_family=ff)
        field_pad = ft.padding.only(left=s(10), top=s(8), right=s(10), bottom=s(8))
        for fld in [result_f, hours_f]:
            fld.text_style = field_style
            fld.hint_style = hint_style
            fld.border_radius = s(6)
            fld.content_padding = field_pad
            fld.dense = True

        body = ft.Container(
            ft.Column([
                ft.Text(t.title[:40], size=s(13), weight=ft.FontWeight.W_500,
                        color=theme.text_primary, font_family=ff),
                ft.Text("交接班日志将作为 AI 审核的提交材料", size=s(11),
                        color=theme.text_secondary, font_family=ff),
                ft.Container(height=s(10)),
                result_f,
                ft.Container(height=s(8)),
                hours_f,
            ], spacing=0, tight=True),
            padding=ft.padding.all(s(14)),
        )
        content = ft.Column([
            dlg_header(ft.Icons.ASSIGNMENT_TURNED_IN_OUTLINED, "提交验收",
                       lambda e: dlg.close()),
            body,
            dlg_footer("取消", "提交验收", submit,
                       on_cancel=lambda e: dlg.close()),
        ], spacing=0, tight=True)
        from app.ui.components.modal_dialog import ModalDialog
        dlg = ModalDialog(self._page, content, width=480)
        dlg.open()

    def _dlg_block(self, tid):
        """阻塞原因弹窗 → parts_hold（与 CreateTaskDialog 风格统一）。"""
        t = state.get_task(tid)
        if not t: return
        ff = theme.font_family

        reason_f = ft.TextField(
            hint_text="如：等待航材、缺工具、等待排故方案...",
            multiline=True, min_lines=3, max_lines=6,
            border_color=theme.border, focused_border_color=theme.warning,
            text_style=ft.TextStyle(color="#e0e0e0", size=s(12), font_family=ff),
            hint_style=ft.TextStyle(color=theme.text_secondary, size=s(11), font_family=ff),
            bgcolor=theme.card, dense=True, border_radius=s(6),
            content_padding=ft.padding.only(left=s(10), top=s(8), right=s(10), bottom=s(8)),
        )

        def _do_block(_):
            reason = (reason_f.value or "").strip()
            if not reason:
                Toast.show(self._page, "请填写阻塞原因", "warning"); return
            try:
                task_service.block_task(tid, reason=reason, user="user")
                dlg.close()
                Toast.show(self._page, "已阻塞，任务移至阻塞中", "success")
            except Exception as e:
                Toast.show(self._page, str(e), "warning")

        from app.ui.components.modal_dialog import ModalDialog
        body = ft.Container(
            ft.Column([
                ft.Text(t.title[:40], size=s(13), weight=ft.FontWeight.W_500,
                        color=theme.text_primary, font_family=ff),
                ft.Container(height=s(10)),
                reason_f,
            ], spacing=0, tight=True),
            padding=ft.padding.all(s(14)),
        )
        content = ft.Column([
            dlg_header(ft.Icons.BLOCK_OUTLINED, "阻塞任务",
                       lambda e: dlg.close()),
            body,
            dlg_footer("取消", "确认阻塞", _do_block,
                       on_cancel=lambda e: dlg.close(),
                       confirm_color=theme.warning),
        ], spacing=0, tight=True)
        dlg = ModalDialog(self._page, content, width=460)
        dlg.open()

    def _dlg_edit(self, task):
        """编辑任务弹窗 — 照搬创建任务弹窗风格，含 AI 补全、日期选择器、状态约束。"""
        ff = theme.font_family
        st = task.status.value

        # ── 状态约束规则 ──
        # backlog: 全部可编辑
        # triage: 锁定 reg/ata/type
        # scheduled: 锁定 reg/ata/priority/type/employee/times/zone
        # ready/in_progress/parts_hold: 锁定除 desc/log 外全部
        # inspection/completed/archived: 全部锁定（仅查看）
        _CORE_LOCKED = st not in ("backlog",)          # reg, ata
        _TYPE_LOCKED = st not in ("backlog",)           # task_type
        _PRI_LOCKED = st not in ("backlog", "triage")   # priority
        _EMP_LOCKED = st not in ("backlog", "triage")   # employee
        _TIME_LOCKED = st not in ("backlog", "triage")  # planned times, hours
        _ZONE_LOCKED = st not in ("backlog", "triage")  # zone
        _TITLE_LOCKED = st in ("ready", "in_progress", "parts_hold",
                               "inspection", "completed", "archived")
        _DESC_LOCKED = st in ("ready", "in_progress", "parts_hold",
                               "inspection", "completed", "archived")
        _LOG_LOCKED = st in ("inspection", "completed", "archived")
        _ALL_LOCKED = st in ("completed", "archived")

        # ── helpers（照搬 create_task_dialog 风格）──
        def _norm_tf(hint="", value="", readonly=False, **kw):
            from app.ui.services.dialog_builder import make_field
            return make_field(hint=hint, value=value, readonly=readonly, **kw)

        def _label(text, required=False):
            from app.ui.services.dialog_builder import make_label
            return make_label(text, required)

        def _col(lbl, ctrl):
            from app.ui.services.dialog_builder import make_col
            return make_col(lbl, ctrl)

        # ── 上下文收集（供 AI 补全）──
        _fields = {}

        def _get_ctx():
            result = {}
            for fn in ["title", "description", "ata_chapter", "aircraft_reg",
                       "employee_id", "employee_name", "zone", "task_type"]:
                ctrl = _fields.get(fn)
                if ctrl is None:
                    result[fn] = ""
                elif hasattr(ctrl, 'value'):
                    result[fn] = ctrl.value or ""
                else:
                    result[fn] = ""
            return result

        def _on_filled(target_field: str, value: str):
            ctrl = _fields.get(target_field)
            if ctrl is None: return
            if hasattr(ctrl, 'text_field'):
                ctrl = ctrl.text_field
            if not isinstance(ctrl, ft.TextField) or not ctrl.read_only:
                ctrl.value = value
                try: ctrl.update()
                except Exception: pass

        # ── 标题 ──
        from app.ui.widgets.ghost_text import GhostTextField
        if _TITLE_LOCKED:
            title_gf = _norm_tf("任务标题", str(task.title), readonly=True)
            _fields["title"] = title_gf
            log.debug("edit", f"title='{task.title}' locked=True (plain TF)")
        else:
            title_gf = GhostTextField(
                hint_text="任务标题", field_name="title",
                get_context=_get_ctx, on_field_filled=_on_filled,
            )
            title_gf.value = task.title
            _fields["title"] = title_gf
            log.debug("edit", f"title='{task.title}' locked=False (GhostTextField)")

        # ── 描述 ──
        if _DESC_LOCKED:
            desc_gf = ft.Text(task.description or "—", size=s(13),
                               color=theme.text_disabled, font_family=ff)
            _fields["description"] = desc_gf
            log.debug("edit", f"desc='{(task.description or '')[:30]}' locked=True (plain TF)")
        else:
            desc_gf = GhostTextField(
                hint_text="任务描述", field_name="description",
                get_context=_get_ctx, on_field_filled=_on_filled,
                multiline=True, min_lines=3,
            )
            desc_gf.value = task.description or ""
            _fields["description"] = desc_gf
            log.debug("edit", f"desc='{(task.description or '')[:30]}' locked=False (GhostTextField)")

        # ── 飞机注册号 ──
        reg_f = _norm_tf("飞机注册号，如 B-5823", str(task.aircraft_reg or ""), readonly=_CORE_LOCKED)
        log.debug("edit", f"reg='{task.aircraft_reg}' locked={_CORE_LOCKED}")
        _fields["aircraft_reg"] = reg_f

        # ── ATA 章节 ──
        if _CORE_LOCKED:
            ata_gf = _norm_tf("ATA 章节，如 32-41-03", str(task.ata_chapter or ""), readonly=True)
            _fields["ata_chapter"] = ata_gf
            log.debug("edit", f"ata='{task.ata_chapter}' locked=True (plain TF)")
        else:
            ata_gf = GhostTextField(
                hint_text="ATA 章节，如 32-41-03", field_name="ata_chapter",
                get_context=_get_ctx, on_field_filled=_on_filled,
            )
            ata_gf.value = task.ata_chapter or ""
            _fields["ata_chapter"] = ata_gf
            log.debug("edit", f"ata='{task.ata_chapter}' locked=False (GhostTextField)")

        # ── 优先级 ──
        _PRI_OPTS = [("aog","AOG",theme.priority_color("aog")),("cat_a","Cat A",theme.priority_color("cat_a")),
                     ("cat_b","Cat B",theme.priority_color("cat_b")),("cat_c","Cat C",theme.priority_color("cat_c")),
                     ("cat_d","Cat D",theme.priority_color("cat_d"))]
        cur_pri = task.priority.value if hasattr(task.priority, 'value') else str(task.priority)
        _sel_pri = [cur_pri]
        _pri_btns = []

        if _PRI_LOCKED:
            # 锁定态：只显示当前优先级彩色标签
            _pri_label = {v: l for v, l, _ in _PRI_OPTS}.get(cur_pri, cur_pri.upper())
            _pri_color = theme.priority_color(cur_pri)
            pri_row = ft.Container(
                ft.Text(_pri_label, size=s(11), color=ft.Colors.WHITE, font_family=ff,
                        weight=ft.FontWeight.W_600),
                padding=ft.padding.symmetric(horizontal=s(12), vertical=s(5)),
                border_radius=s(4), bgcolor=_pri_color,
            )
        else:
            def _mk_pb(v, l, c):
                sel = (v == _sel_pri[0])
                b = ft.Container(
                    ft.Text(l, size=s(10),
                            color=c if not sel else ft.Colors.WHITE,
                            font_family=ff, weight=ft.FontWeight.W_600),
                    padding=ft.padding.symmetric(horizontal=s(10), vertical=s(5)),
                    border_radius=s(4),
                    bgcolor=c if sel else ft.Colors.TRANSPARENT,
                    border=ft.border.all(1, c),
                    on_click=lambda e, x=v: _on_pri(x))
                _pri_btns.append((v, b))
                return b

            def _on_pri(v):
                _sel_pri[0] = v
                for pv, b in _pri_btns:
                    c = theme.priority_color(pv); b.bgcolor = c if pv == v else ft.Colors.TRANSPARENT
                    b.content.color = ft.Colors.WHITE if pv == v else c; b.update()

            pri_row = ft.Row([_mk_pb(v, l, c) for v, l, c in _PRI_OPTS], spacing=s(6), tight=True)

        # ── 任务类型 ──
        cur_tt = task.task_type.value if hasattr(task.task_type, 'value') else str(task.task_type)
        type_dd = ft.Dropdown(value=cur_tt, dense=True, disabled=_TYPE_LOCKED,
            options=[ft.dropdown.Option(k, v) for k, v in [
                ("troubleshoot","排故"),("inspection","检查"),("servicing","勤务"),
                ("removal_install","拆装"),("test","测试"),("repair","修复")]],
            border_color=theme.border,
            focused_border_color=theme.info, bgcolor=theme.card,
            text_style=ft.TextStyle(color="#e0e0e0", size=s(12), font_family=ff),
            border_radius=s(6))
        _fields["task_type"] = type_dd

        # ── 员工 ──
        emp_id_f = _norm_tf("员工 ID，如 ZH001", str(task.employee_id or ""), readonly=_EMP_LOCKED)
        emp_name_f = _norm_tf("员工姓名，如 张工", str(task.employee_name or ""), readonly=_EMP_LOCKED)
        log.debug("edit", f"emp_id='{task.employee_id}' name='{task.employee_name}' locked={_EMP_LOCKED}")
        _fields["employee_id"] = emp_id_f
        _fields["employee_name"] = emp_name_f
        if not _EMP_LOCKED:
            def _on_emp_id(e):
                val = (e.control.value or "").strip()
                if not val:
                    emp_name_f.value = ""
                    try: emp_name_f.update()
                    except Exception: pass
                    return
                from app.core.services.employee_service import employee_service
                emp = employee_service.get_employee(val)
                if emp:
                    emp_name_f.value = emp["name"] if emp.get("available", True) else f"{emp['name']}(不可用)"
                else:
                    emp_name_f.value = "未知员工"
                try: emp_name_f.update()
                except Exception: pass
            emp_id_f.on_change = _on_emp_id

        # ── 时间（照搬 create_task_dialog 的日期选择器）──
        from datetime import datetime as dt
        sh = _norm_tf("08", value=(task.planned_start.strftime("%H") if task.planned_start else "08"),
                       width=s(56), readonly=_TIME_LOCKED)
        sm = _norm_tf("00", value=(task.planned_start.strftime("%M") if task.planned_start else "00"),
                       width=s(56), readonly=_TIME_LOCKED)
        eh = _norm_tf("12", value=(task.planned_end.strftime("%H") if task.planned_end else "12"),
                       width=s(56), readonly=_TIME_LOCKED)
        em = _norm_tf("00", value=(task.planned_end.strftime("%M") if task.planned_end else "00"),
                       width=s(56), readonly=_TIME_LOCKED)
        hrs_str = f"{task.estimated_hours:.1f}" if task.estimated_hours else ""
        hours_f = _norm_tf("（可选）", value=hrs_str, width=120, readonly=_TIME_LOCKED)
        log.debug("edit", f"planned_start={task.planned_start} planned_end={task.planned_end} hrs={task.estimated_hours} locked={_TIME_LOCKED}")

        # 仅 backlog/triage 有时分校验
        if not _TIME_LOCKED:
            def _clamp_tf(tf, hi):
                from app.ui.services.dialog_builder import clamp_time_field
                clamp_time_field(tf, hi); tf.update()
            for _tf, _hi in [(sh, 23), (sm, 59), (eh, 23), (em, 59)]:
                _tf.on_blur = lambda e, t=_tf, h=_hi: _clamp_tf(t, h)

        from app.ui.services.dialog_builder import make_date_picker as _mkdp

        if _TIME_LOCKED:
            start_date_ctrl = ft.Text(
                task.planned_start.strftime("%Y-%m-%d %H:%M") if task.planned_start else "—",
                size=s(13), color=theme.text_disabled, font_family=ff)
            due_date_ctrl = ft.Text(
                task.planned_end.strftime("%Y-%m-%d %H:%M") if task.planned_end else "—",
                size=s(13), color=theme.text_disabled, font_family=ff)
            start_date_state = due_date_state = {"date": None}
            start_date_err = due_date_err = lambda m: None
            start_date_clr = due_date_clr = lambda: None
        else:
            start_date_ctrl, start_date_state, start_date_err, start_date_clr = _mkdp(
                self._page, task.planned_start, locked=_TIME_LOCKED,
                on_pick_callback=lambda: _recalc_hours())
            due_date_ctrl, due_date_state, due_date_err, due_date_clr = _mkdp(
                self._page, task.planned_end, locked=_TIME_LOCKED,
                on_pick_callback=lambda: _recalc_hours())

        def _get_dt(date_state, h_f, m_f):
            from app.ui.services.dialog_builder import build_datetime
            return build_datetime(date_state, h_f, m_f)

        def _recalc_hours():
            if _TIME_LOCKED: return
            sd_dt = _get_dt(start_date_state, sh, sm)
            ed_dt = _get_dt(due_date_state, eh, em)
            if sd_dt and ed_dt:
                diff = (ed_dt - sd_dt).total_seconds() / 3600
                if diff > 0:
                    hours_f.value = f"{diff:.1f}"
                    try: hours_f.update()
                    except Exception: pass
                else:
                    due_date_state["date"] = None; eh.value = ""; em.value = ""
                    try: eh.update(); em.update()
                    except Exception: pass
                    due_date_clr()
                    hours_f.value = ""
                    try: hours_f.update()
                    except Exception: pass
                    from app.ui.widgets.toast import Toast
                    Toast.show(self._page, "完成时间必须晚于开始时间", "warning")

        def _date_row(label_text, date_ctrl, h_f, m_f):
            return ft.Row([
                ft.Text(label_text, size=s(11), color=theme.text_secondary, font_family=ff, width=s(36)),
                ft.Container(content=date_ctrl, expand=True),
                h_f,
                ft.Text("时", size=s(11), color=theme.text_secondary, font_family=ff),
                m_f,
                ft.Text("分", size=s(11), color=theme.text_secondary, font_family=ff),
            ], spacing=s(4), vertical_alignment=ft.CrossAxisAlignment.CENTER)

        # ── 区域 ──
        zone_f = _norm_tf("区域 (Zone)，如 710", str(task.zone or ""), readonly=_ZONE_LOCKED)
        log.debug("edit", f"zone='{task.zone}' locked={_ZONE_LOCKED}")
        _fields["zone"] = zone_f

        # ── 交接班日志 ──
        if _LOG_LOCKED:
            log_f = ft.Text(task.shift_handover_log or "—", size=s(13),
                            color=theme.text_disabled, font_family=ff)
        else:
            log_f = ft.TextField(
                label="交接班日志", value=task.shift_handover_log or "",
                border_color=theme.border, focused_border_color=theme.info,
                text_style=ft.TextStyle(color="#e0e0e0", size=s(13), font_family=ff),
                bgcolor=theme.card, multiline=True, min_lines=2, max_lines=5,
                border_radius=s(6), dense=True,
            )

        # ── 保存 ──
        def save(_):
            from app.ui.widgets.toast import Toast
            if not _TITLE_LOCKED:
                ttl = (title_gf.value or "").strip()
                if not ttl:
                    Toast.show(self._page, "请输入标题", "warning"); return
            else:
                ttl = task.title

            changes = {}
            if not _TITLE_LOCKED:
                changes["title"] = ttl
            if not _DESC_LOCKED:
                changes["description"] = (desc_gf.value or "").strip()
            if not _CORE_LOCKED:
                changes["aircraft_reg"] = (reg_f.value or "").strip().upper()
                changes["ata_chapter"] = (ata_gf.value or "").strip()
            if not _PRI_LOCKED:
                changes["priority"] = _sel_pri[0]
            if not _TYPE_LOCKED:
                changes["task_type"] = type_dd.value or "troubleshoot"
            if not _EMP_LOCKED:
                eid = (emp_id_f.value or "").strip()
                ename = (emp_name_f.value or "").strip()
                changes["employee_id"] = eid
                changes["employee_name"] = ename
                if ename:
                    changes["assignee"] = ename
            if not _TIME_LOCKED:
                ps = _get_dt(start_date_state, sh, sm)
                pe = _get_dt(due_date_state, eh, em)
                changes["planned_start"] = ps
                changes["planned_end"] = pe
                try:
                    hv = (hours_f.value or "").strip()
                    changes["estimated_hours"] = float(hv) if hv else 0.0
                except ValueError:
                    pass
            if not _ZONE_LOCKED:
                changes["zone"] = (zone_f.value or "").strip()
            if not _LOG_LOCKED:
                changes["shift_handover_log"] = (log_f.value or "").strip()

            task_service.update_task(task.id, **changes)
            _close_dlg()
            self._refresh_board()
            Toast.show(self._page, "任务已更新", "success")

        # ── 组装 ──
        sep = ft.Divider(height=s(10), color=ft.Colors.TRANSPARENT)
        header = ft.Container(
            ft.Row([
                ft.Icon(ft.Icons.EDIT_OUTLINED, size=s(15), color="#5294e2"),
                ft.Text("编辑任务", size=s(14), weight=ft.FontWeight.W_600,
                        color=theme.text_primary, font_family=ff),
                ft.Container(expand=True),
                ft.Text(f"{task.status.value} | {task.work_order_id or task.id}",
                        size=s(10), color=theme.text_secondary, font_family=ff),
                ft.Container(width=s(8)),
                ft.IconButton(ft.Icons.CLOSE, icon_size=s(16), icon_color=theme.text_secondary,
                    style=ft.ButtonStyle(bgcolor=ft.Colors.TRANSPARENT, overlay_color=ft.Colors.RED_900,
                        shape=ft.RoundedRectangleBorder(radius=s(4))),
                    on_click=lambda e: _close_dlg()),
            ], spacing=s(8)),
            padding=ft.padding.only(left=s(14), top=s(8), right=s(6), bottom=s(8)),
            border=ft.border.only(bottom=ft.BorderSide(1, theme.border)),
        )

        form = ft.Container(
            ft.Column([
                _label("任务标题", required=not _TITLE_LOCKED), title_gf, sep,
                _label("任务描述"), desc_gf, sep,
                ft.Row([_col(_label("飞机注册号", required=not _CORE_LOCKED), reg_f),
                        _col(_label("ATA 章节", required=not _CORE_LOCKED), ata_gf)], spacing=s(12)), sep,
                ft.Row([_col(_label("员工 ID"), emp_id_f),
                        _col(_label("员工姓名"), emp_name_f)], spacing=s(12)), sep,
                _label("优先级"), pri_row, sep,
                ft.Row([_col(_label("任务类型"), type_dd),
                        ft.Container(width=s(12)),
                        _col(_label("计划工时"), hours_f)], spacing=s(0)), sep,
                _label("计划时间"),
                _date_row("开始", start_date_ctrl, sh, sm),
                ft.Container(height=s(4)),
                _date_row("完成", due_date_ctrl, eh, em), sep,
                ft.Row([_col(_label("区域"), zone_f)], spacing=s(12)), sep,
                _label("交接班日志"), log_f,
            ], spacing=s(4), tight=True),
            padding=ft.padding.only(left=s(14), top=s(14), right=s(14), bottom=s(14)),
        )

        # parts_hold 取消阻塞按钮
        extra_btns = []
        if st == "parts_hold" and task.is_blocked:
            def _unblock(e):
                try:
                    task_service.unblock_task(task.id, user="user")
                    _close_dlg(); self._refresh_board()
                    from app.ui.widgets.toast import Toast
                    Toast.show(self._page, "已取消阻塞", "success")
                except Exception as ex:
                    from app.ui.widgets.toast import Toast
                    Toast.show(self._page, f"取消失败: {ex}", "error")
            extra_btns.append(
                ft.OutlinedButton("取消阻塞", icon=ft.Icons.LOCK_OPEN_OUTLINED,
                    on_click=_unblock,
                    style=ft.ButtonStyle(
                        color=theme.error, side=ft.BorderSide(1, theme.error),
                        shape=ft.RoundedRectangleBorder(radius=s(6)),
                        padding=ft.padding.symmetric(horizontal=s(12), vertical=s(6)),
                        text_style=ft.TextStyle(size=s(11), font_family=ff))))

        btn_st = ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=s(6)),
            padding=ft.padding.only(left=s(18), top=s(7), right=s(18), bottom=s(7)),
            text_style=ft.TextStyle(size=s(12), font_family=ff))
        footer = ft.Container(
            ft.Row(extra_btns + [
                ft.Container(expand=True),
                ft.TextButton("取消", on_click=lambda e: _close_dlg(),
                    style=ft.ButtonStyle(shape=btn_st.shape, padding=btn_st.padding,
                        text_style=btn_st.text_style, side=ft.BorderSide(1, theme.border),
                        color=theme.text_secondary)),
                ft.ElevatedButton("保存", on_click=save,
                    style=ft.ButtonStyle(shape=btn_st.shape, padding=btn_st.padding,
                        text_style=btn_st.text_style, bgcolor="#5294e2",
                        color=ft.Colors.WHITE, elevation=0)),
            ], spacing=s(8)),
            padding=ft.padding.only(left=s(14), top=s(8), right=s(14), bottom=s(10)),
            border=ft.border.only(top=ft.BorderSide(1, theme.border)),
        )

        log.debug("edit", f"opening dialog: st={st} locked={{core:{_CORE_LOCKED} pri:{_PRI_LOCKED} type:{_TYPE_LOCKED} emp:{_EMP_LOCKED} time:{_TIME_LOCKED} zone:{_ZONE_LOCKED} title:{_TITLE_LOCKED} desc:{_DESC_LOCKED} log:{_LOG_LOCKED}}}")

        # 照搬 CreateTaskDialog 的定位逻辑：OverlayDimmer + Stack 绝对定位
        PW, PH = 700, 750
        cx = max(0, (self._page.width - PW) // 2)
        cy = max(10, (self._page.height - PH) // 2)

        from app.ui.widgets.overlay_dimmer import OverlayDimmer
        panel = ft.Container(
            content=ft.Column([header,
                ft.ListView([form], spacing=0, expand=True, padding=0),
                footer], spacing=0, tight=True),
            width=PW, height=PH,
            bgcolor=theme.surface, border_radius=s(10),
            border=ft.border.all(1, theme.border),
            shadow=ft.BoxShadow(spread_radius=1, blur_radius=20, color="#000000aa"),
            left=cx, top=cy,
        )

        _dimmer_ref = [None]
        def _close_dlg():
            if _dimmer_ref[0]:
                _dimmer_ref[0].close()
        _dimmer_ref[0] = OverlayDimmer.open(self._page, panel, dim_opacity=0.55,
                                             on_dimmer_click=_close_dlg)

    def _dlg_filter(self):
        ff = theme.font_family

        def _dropdown(options, width=220):
            return ft.Dropdown(
                dense=True,
                options=[ft.dropdown.Option(k, v) for k, v in options],
                border_color=theme.border,
                focused_border_color=theme.info,
                bgcolor=theme.card,
                text_style=ft.TextStyle(
                    color="#e0e0e0", size=s(12), font_family=ff),
                border_radius=s(6),
                width=width,
            )

        def _label(text):
            return ft.Text(text, size=s(12), color=theme.text_primary,
                           font_family=ff, weight=ft.FontWeight.W_500)

        ata_dd = _dropdown([
            ("", "全部 ATA"),
            ("21", "21 - 空调"), ("24", "24 - 电源"), ("27", "27 - 飞行控制"),
            ("28", "28 - 燃油"), ("32", "32 - 起落架"), ("49", "49 - APU"),
            ("72", "72 - 发动机"), ("79", "79 - 滑油")])
        pri_dd = _dropdown([
            ("", "全部优先级"),
            ("aog", "AOG"), ("cat_a", "Cat A"),
            ("cat_b", "Cat B"), ("cat_c", "Cat C")])

        def _apply(_):
            f = FilterState()
            if ata_dd.value: f.ata_chapters = [ata_dd.value]
            if pri_dd.value: f.priorities = [pri_dd.value]
            board_service.set_filters(f)
            dlg.close()
            Toast.show(self._page, "筛选已应用", "info")

        def _clear(_):
            ata_dd.value = ""
            pri_dd.value = ""
            ata_dd.update(); pri_dd.update()
            board_service.set_filters(FilterState())
            dlg.close()
            Toast.show(self._page, "筛选已清除", "info")

        from app.ui.components.modal_dialog import ModalDialog

        form = ft.Container(
            ft.Column([
                _label("ATA 章节"),
                ata_dd,
                ft.Divider(height=s(14), color=ft.Colors.TRANSPARENT),
                _label("优先级"),
                pri_dd,
            ], spacing=s(4), tight=True),
            padding=ft.padding.only(left=s(14), top=s(14), right=s(14), bottom=s(14)),
        )

        content = ft.Column([
            dlg_header(ft.Icons.FILTER_ALT_OUTLINED, "筛选任务",
                       lambda e: dlg.close()),
            form,
            dlg_footer("清除", "应用筛选", _apply,
                       on_cancel=_clear),
        ], spacing=0, tight=True)
        dlg = ModalDialog(self._page, content, width=360)
        dlg.open()


