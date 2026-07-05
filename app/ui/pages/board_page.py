"""看板主页面."""

import threading
import time
import traceback
from datetime import datetime

import flet as ft

from app.agent.active_task import active_task_registry
from app.config.theme import theme, s
from app.core.logging import log
from app.core.models.kanban import FilterState
from app.core.services.board_service import board_service
from app.core.services.task_service import task_service
from app.core.state import state
from app.ui.components.ai_chat import AIChatPanel
from app.ui.components.ai_suggestion import FleetStatusBar
from app.ui.components.bottom_status_bar import BottomStatusBar
from app.ui.components.command_bar import CommandBar
from app.ui.components.kanban_board import KanbanBoard
from app.ui.components.side_panel import SidePanel
from app.ui.services.ai_commands import AICommands
from app.ui.services.task_registry import TaskRegistry
from app.ui.widgets.toast import Toast


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
        self._search_clear_btn = None               # 由 app.py 外部赋值
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
        self._empty_result_dlg = None         # OverlayDimmer ref
        self._report_thread = None            # threading.Thread ref
        self._review_thread = None            # threading.Thread ref
        self._selected_tid: str | None = None  # 右键选中高亮
        self._ai_active_tid: str | None = None # AI 运行高亮
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
        from app.ui.services.card_highlighter import CardHighlighter
        CardHighlighter.init(self.kanban_board)
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

        # ── AI 命令模块 ──
        self._ai = AICommands(self)

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
            cursor_color=theme.accent,
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

        # ── 遮罩槽位（Flet 原生布局自动填充窗口，缩放时实时响应）──
        self._dimmer_slot = ft.Container(visible=False, expand=True)

        # ── 主布局（无顶栏，顶栏已合并到窗口标题栏）──
        main_content = ft.Container(
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
        # 注册原生遮罩槽位（Flet 自动布局→缩放时实时响应）
        from app.ui.widgets.overlay_dimmer import OverlayDimmer
        OverlayDimmer.init_slot(self)
        # Stack: 主内容(底层) + 遮罩槽位(顶层, expand 由 Flet 自动填满)
        return ft.Stack([
            main_content,
            self._dimmer_slot,
        ], expand=True)

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
        log.info("ghost.accept", task_id=tid[:8]); Toast.show(self._page, "AI 建议已接受", "success")
        self._refresh_board()

    def _reject_ai_task(self, tid):
        """拒绝 AI 建议任务——委托 ProposalHandler 执行业务变更。"""
        t = state.get_task(tid)
        title = t.title if t else ""
        from app.ui.services.proposal_handler import ProposalHandler
        ProposalHandler.reject(tid)
        self._sync_chat_proposal(tid, "rejected", title)
        log.info("ghost.reject", task_id=tid[:8]); Toast.show(self._page, "AI 建议已拒绝", "info")
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
        # 所有幽灵卡片已处理 → 完成状态栏中等待/进行中的任务
        for t in self._task_registry.get_all():
            if t.get("status") in ("等待确认", "准备中..."):
                label = t["label"]
                self._task_registry.update_status(t["id"], "已完成", 1.0)
                if self.ai_chat:
                    try:
                        self.ai_chat.update_task_card("已完成", border_color=theme.success)
                        self.ai_chat.show_status_bubble(f"{label} 完成", theme.success)
                    except Exception:
                        pass
                    def _delayed_hide():
                        time.sleep(2)
                        try:
                            if self.ai_chat:
                                self.ai_chat.hide_task_card()
                        except Exception:
                            pass
                    threading.Thread(target=_delayed_hide, daemon=True).start()
                def _delayed_unregister(tid=t["id"]):
                    time.sleep(5)
                    self._task_registry.unregister(tid)
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
        from app.ui.services.card_highlighter import CardHighlighter
        active_task_registry.clear()
        CardHighlighter.clear_ai_running()  # 橙色高亮
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
        log.info("task.cancel", task_id=task_id[:20])
        from app.ui.services.card_highlighter import CardHighlighter
        for t in self._task_registry.get_all():
            if t["id"] == task_id:
                ttype = t.get("type", "")
                log.info("task.cancel", f"type={ttype}")
                if ttype == "report":
                    self._cancel_report()
                elif ttype == "review":
                    self._cancel_review()
                else:
                    CardHighlighter.clear_ai_running()  # 橙色高亮
                    label = t.get("label", "")
                    if self.ai_chat:
                        ce = self._runner.get_cancel()
                        if ce:
                            ce.set()
                        self.ai_chat.update_task_card("已取消", border_color=theme.text_disabled)
                        self.ai_chat.show_status_bubble(f"{label} 已取消", theme.text_disabled)
                    self._reject_all_proposals(task_id)
                    self._force_clear_all_ghosts(task_id)
                    self._task_registry.update_status(task_id, "已取消", 0)
                    Toast.show(self._page, "任务已取消", "info")
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
        log.info("task.cancel", f"task_id not found in registry")

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
        # 单任务 AI：拒绝指定任务（仅当 AI 已修改过任务时才调用 Handler）
        for prefix in ("classify_", "schedule_", "review_"):
            if task_id.startswith(prefix):
                real_tid = task_id[len(prefix):]
                if real_tid:
                    t = state.get_task(real_tid)
                    if t and t.ai_proposed:
                        ProposalHandler.reject(real_tid)
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
                            bgcolor=theme.accent, color=ft.Colors.WHITE, elevation=0)),
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
            shadow=ft.BoxShadow(spread_radius=1, blur_radius=20, color=theme.dialog_shadow),
            left=cx, top=cy,
        )
        from app.ui.widgets.overlay_dimmer import OverlayDimmer
        # 关闭已有弹窗防止叠加
        if self._empty_result_dlg:
            try: self._empty_result_dlg.close()
            except Exception: pass
        dlg = OverlayDimmer.open(self._page, panel, dim_opacity=0.4,
                                  on_dimmer_click=lambda: dlg.close(),
                                  on_close=lambda: setattr(self, '_empty_result_dlg', None))
        self._empty_result_dlg = dlg

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
        Toast.show(self._page, "报表任务已取消", "info")

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
        Toast.show(self._page, "审核任务已取消", "info")

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
        from app.ui.services.card_highlighter import CardHighlighter
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
        CardHighlighter.select(tid)  # 蓝色高亮（在 close_current_menu→deselect 之后）

    @staticmethod
    def _get_cursor_pos(page) -> tuple[float, float]:
        """Win32 API 获取鼠标在页面客户区内的坐标（不依赖 Flet 事件）。"""
        import ctypes
        from ctypes import wintypes  # type: ignore[attr-defined]
        try:
            pt = wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))       # type: ignore[attr-defined]
            hwnd = ctypes.windll.user32.FindWindowW(None, "TaskSense") # type: ignore[attr-defined]
            if hwnd:
                ctypes.windll.user32.ScreenToClient(hwnd, ctypes.byref(pt))  # type: ignore[attr-defined]
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
        from app.ui.dialogs.priority_dialog import open as dlg_priority
        dlg_priority(self._page, tid, col, index)

    def _dlg_schedule(self, tid, col=None, index=-1, move_to=True):
        from app.ui.dialogs.schedule_dialog import open as dlg_schedule
        dlg_schedule(self._page, tid, col, index, move_to)

    def _on_column_menu(self, cid):
        Toast.show(self._page, f"列操作: {cid}", "info")

    def _on_create_task(self, e):
        from app.ui.components.create_task_dialog import CreateTaskDialog
        CreateTaskDialog.open(self._page)

    def _on_settings_click(self, e):
        from app.ui.pages.settings_window import SettingsOverlay
        SettingsOverlay.open(self._page)

    def _open_employee_page(self):
        from app.ui.pages.employee_page import EmployeeWorkbench
        EmployeeWorkbench.open(self._page)

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
            self._search_box.border = ft.border.all(1, theme.accent)
            self._search_box.update()

    def _on_search_blur(self):
        if self._search_box:
            self._search_box.border = ft.border.all(1, theme.border_active)
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
        self._ai._cmd_outline()

        
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
        self._ai._cmd_gen_tasks()

        
        def _do_gen():
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
        self._ai._cmd_classify()

    def _cmd_schedule(self):
        self._ai._cmd_schedule()

    def _cmd_acceptance(self):
        log.debug("acceptance", "===== _cmd_acceptance called =====")
        self._ai._cmd_acceptance()

    def _cmd_report(self):
        self._ai._cmd_report()
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
            text_style=ft.TextStyle(color=theme.text_content, size=s(11), font_family=ff),
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
                ft.Icon(ft.Icons.ASSESSMENT_OUTLINED, size=s(15), color=theme.accent),
                ft.Text("生成维护报表", size=s(14), weight=ft.FontWeight.W_600,
                        color=theme.text_primary, font_family=ff),
                progress,
                ft.Container(expand=True),
                ft.IconButton(ft.Icons.MINIMIZE_OUTLINED, icon_size=s(15),
                              icon_color=theme.text_secondary,
                              tooltip="最小化后台运行",
                              style=ft.ButtonStyle(
                                  bgcolor=ft.Colors.TRANSPARENT,
                                  overlay_color=theme.card_hover,
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
                        bgcolor=theme.accent, color=ft.Colors.WHITE, elevation=0)),
            ]
        else:
            footer_btns = [
                ft.Container(expand=True),
                ft.ElevatedButton("保存报表", on_click=_save,
                    style=ft.ButtonStyle(
                        shape=btn_st.shape, padding=btn_st.padding,
                        text_style=btn_st.text_style,
                        bgcolor=theme.accent, color=ft.Colors.WHITE, elevation=0)),
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
            shadow=ft.BoxShadow(spread_radius=1, blur_radius=20, color=theme.dialog_shadow),
            left=cx, top=cy,
        )

        from app.ui.widgets.overlay_dimmer import OverlayDimmer
        # 关闭已有报表弹窗防止叠加
        if self._report_dlg:
            try: self._report_dlg.close()
            except Exception: pass
        dlg = OverlayDimmer.open(self._page, panel, dim_opacity=0.55,
                                  on_close=lambda: setattr(self, '_report_dlg', None))
        self._report_dlg = dlg

        # ── 异步生成（仅加载中且无运行中线程时）──
        if is_loading and (self._report_thread is None or not self._report_thread.is_alive()):
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
                self._task_registry.unregister("report")
            t = threading.Thread(target=_gen, daemon=True)
            self._report_thread = t
            t.start()

    # ═══════════════════════════════════════════
    # 7. 任务审核 → 弹窗显示合规问题
    # ═══════════════════════════════════════════

    def _cmd_review(self):
        self._ai._cmd_review()
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
                ft.Icon(ft.Icons.FACT_CHECK_OUTLINED, size=s(15), color=theme.accent),
                ft.Text("任务合规审核", size=s(14), weight=ft.FontWeight.W_600,
                        color=theme.text_primary, font_family=ff),
                review_summary_container,
                ft.Container(expand=True),
                ft.IconButton(ft.Icons.MINIMIZE_OUTLINED, icon_size=s(15),
                              icon_color=theme.text_secondary,
                              tooltip="最小化后台运行",
                              style=ft.ButtonStyle(
                                  bgcolor=ft.Colors.TRANSPARENT,
                                  overlay_color=theme.card_hover,
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
                        bgcolor=theme.accent, color=ft.Colors.WHITE, elevation=0)),
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
            shadow=ft.BoxShadow(spread_radius=1, blur_radius=20, color=theme.dialog_shadow),
            left=cx, top=cy,
        )

        from app.ui.widgets.overlay_dimmer import OverlayDimmer
        dlg = OverlayDimmer.open(self._page, panel, dim_opacity=0.55,
                                  on_close=lambda: setattr(self, '_review_dlg', None))
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
        sc: list = [ft.Text(f"审核 {tasks_r} 个任务", size=s(11),
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

    # ── 右键动作注册表: action → handler(tid, task) ──
    _ACTION_HANDLERS = None  # 懒初始化

    def _init_action_handlers(self):
        """初始化右键菜单动作分发注册表（添加新动作只需在这里注册）。"""
        self._ACTION_HANDLERS = {
            "edit":             self._act_edit,
            "delete":           self._act_delete,
            "search":           self._act_search,
            "ai_explain":       self._act_ai_explain,
            "ai_review":        self._act_ai_review,
            "ai_classify":      self._act_ai_classify,
            "ai_schedule":      self._act_ai_schedule,
            "ai_review_single": self._act_ai_review_single,
            "block":            self._act_block,
            "unblock":          self._act_unblock,
            "set_priority":     self._act_set_priority,
            "change_priority":  self._act_change_priority,
            "schedule":         self._act_schedule,
            "reschedule":       self._act_reschedule,
            "archive_now":      self._act_archive_now,
            "approve":          self._act_approve,
        }

    def _card_action(self, tid, action):
        """右键菜单动作分发（注册表模式）。"""
        from app.ui.services.card_highlighter import CardHighlighter
        t = state.get_task(tid)
        if not t:
            return
        # 清除右键选中高亮（菜单已执行动作）
        CardHighlighter.deselect()
        # 单任务 AI 动作 → 橙色运行高亮
        if action in ("ai_explain", "ai_classify", "ai_schedule",
                       "ai_review_single", "search"):
            CardHighlighter.set_ai_running(tid)
        # 懒初始化
        if self._ACTION_HANDLERS is None:
            self._init_action_handlers()
        # 精确匹配
        handler = self._ACTION_HANDLERS.get(action)
        if handler:
            handler(tid, t)
            return
        # move_to:<col> 模式
        if action.startswith("move_to:"):
            return self._act_move_to(tid, action.split(":", 1)[1])

    # ── 动作处理方法（按需查阅）──

    def _act_edit(self, tid, t):       self._dlg_edit(t)
    def _act_delete(self, tid, t):     task_service.delete_task(tid); self.side_panel and self.side_panel.close(); Toast.show(self._page, "已删除", "info")
    def _act_ai_review(self, tid, t):  self._cmd_acceptance()
    def _act_block(self, tid, t):      self._dlg_block(tid)
    def _act_set_priority(self, tid, t):    self._dlg_priority(tid, "triage", -1)
    def _act_change_priority(self, tid, t): self._dlg_priority(tid)
    def _act_schedule(self, tid, t):        self._dlg_schedule(tid, "scheduled", -1)
    def _act_reschedule(self, tid, t):      self._dlg_schedule(tid, move_to=False)

    def _act_search(self, tid, t):
        from app.ui.services.agent_service import AgentService
        self._run_ai_action("AI 查找文档",
            {"id": tid, "title": t.title, "ata_chapter": t.ata_chapter,
             "aircraft_reg": t.aircraft_reg, "aircraft_model": t.aircraft_model or "",
             "fault_code": getattr(t, 'fault_code', '') or ""},
            lambda ci, ce: AgentService.search_docs(ci, ce), f"search_{tid}")

    def _act_ai_explain(self, tid, t):
        from app.ui.services.agent_service import AgentService
        self._run_ai_action("AI 解释任务",
            {"id": tid, "title": t.title, "description": t.description or "",
             "aircraft_reg": t.aircraft_reg, "aircraft_model": t.aircraft_model or "",
             "ata_chapter": t.ata_chapter, "task_type": t.task_type.value,
             "priority": t.priority.value, "zone": t.zone or "",
             "work_order_id": t.work_order_id, "estimated_hours": t.estimated_hours,
             "is_rii": t.is_rii},
            lambda ci, ce: AgentService.explain_task(ci, ce), f"explain_{tid}")

    def _act_ai_classify(self, tid, t):
        from app.ui.services.agent_service import AgentService
        self._run_ai_action("AI 分类此任务",
            {"id": tid, "title": t.title, "description": t.description or "",
             "aircraft_reg": t.aircraft_reg, "ata_chapter": t.ata_chapter,
             "task_type": t.task_type.value, "aircraft_model": t.aircraft_model or ""},
            lambda ci, ce: AgentService.classify_single(ci, ce), f"classify_{tid}", keep_open=True)

    def _act_ai_schedule(self, tid, t):
        from app.ui.services.agent_service import AgentService
        self._run_ai_action("AI 排程此任务",
            {"id": tid, "title": t.title, "description": t.description or "",
             "aircraft_reg": t.aircraft_reg, "ata_chapter": t.ata_chapter,
             "task_type": t.task_type.value, "priority": t.priority.value,
             "zone": t.zone or "", "estimated_hours": t.estimated_hours},
            lambda ci, ce: AgentService.schedule_single(ci, ce), f"schedule_{tid}", keep_open=True)

    def _act_ai_review_single(self, tid, t):
        from app.ui.services.agent_service import AgentService
        self._run_ai_action("AI 验收此任务",
            {"id": tid, "title": t.title, "description": t.description or "",
             "aircraft_reg": t.aircraft_reg, "aircraft_model": t.aircraft_model or "",
             "ata_chapter": t.ata_chapter, "task_type": t.task_type.value,
             "priority": t.priority.value, "zone": t.zone or "",
             "employee_name": t.employee_name or "", "employee_id": t.employee_id or "",
             "estimated_hours": t.estimated_hours, "actual_hours": t.actual_hours,
             "shift_handover_log": t.shift_handover_log or "(无)",
             "is_rii": t.is_rii, "checklist_progress": t.checklist_progress()},
            lambda ci, ce: AgentService.review_single(ci, ce), f"review_{tid}", keep_open=True)

    def _act_unblock(self, tid, t):
        try:
            task_service.unblock_task(tid, "user")
            Toast.show(self._page, "已取消阻塞，任务返回就绪", "success")
        except Exception as e:
            Toast.show(self._page, str(e), "warning")

    def _act_archive_now(self, tid, t):
        try: task_service.move_task(tid, "archived", changed_by="user"); Toast.show(self._page, "已归档", "success")
        except Exception as e: Toast.show(self._page, str(e), "warning")

    def _act_approve(self, tid, t):
        try: task_service.move_task(tid, "completed", changed_by="user"); Toast.show(self._page, "验收通过", "success")
        except Exception as e: Toast.show(self._page, str(e), "warning")

    def _act_move_to(self, tid, target_col):
        try:
            task_service.move_task(tid, target_col, changed_by="user")
            col_titles = {"ready": "已标记就绪", "in_progress": "已开始执行",
                          "scheduled": "已退回已排程", "triage": "已退回已分类",
                          "backlog": "已退回待处理", "archived": "已归档", "completed": "已完成"}
            Toast.show(self._page, col_titles.get(target_col, f"已移至{target_col}"), "success")
        except Exception as e:
            Toast.show(self._page, str(e), "warning")

    def _start_ghost_polling(self, session_id: str, label: str):
        """定期检查幽灵卡片是否已全部处理，若是则完成任务卡片。"""
        def _poll():
            for _ in range(30):  # 最多轮询 60 秒
                time.sleep(2)
                found = False
                for t in self._task_registry.get_all():
                    if t["id"] == session_id:
                        found = True
                        if t.get("status") not in ("等待确认",):
                            return
                        break
                if not found:
                    return
                proposed = [t for t in state.get_all_tasks() if t.ai_proposed]
                if not proposed:
                    log.debug("ghost_poll", f"all ghosts resolved, completing {session_id}")
                    self._check_ghost_pending_completion()
                    return
        threading.Thread(target=_poll, daemon=True).start()

    def _run_ai_action(self, label: str, task_info: dict,
                       action_fn, session_id: str, keep_open: bool = False):
        self._ai.run_ai_action(label, task_info, action_fn, session_id, keep_open)

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

    def _dlg_block(self, tid):
        from app.ui.dialogs.block_dialog import open as dlg_block
        dlg_block(self._page, tid)

    def _dlg_edit(self, task):
        from app.ui.dialogs.edit_dialog import open as dlg_edit
        dlg_edit(self._page, task)

    def _dlg_filter(self):
        from app.ui.dialogs.filter_dialog import open as dlg_filter
        dlg_filter(self._page)
