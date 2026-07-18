# -*- coding: utf-8 -*-
"""AI 命令处理 — 7 个 AI 工具命令 + 报表/审核弹窗 + _run_ai_action。

从 board_page.py 提取，通过 bp 引用访问 BoardPage 的方法和控件。
"""

import threading
import time
import traceback
from datetime import datetime

from app.agent.active_task import active_task_registry
from app.config.theme import theme
from app.core.logging import log
from app.core.state import state
from app.ui.services.agent_service import AgentService
from app.ui.widgets.toast import Toast


class AICommands:
    """AI 工具命令集合。通过 bp 访问 BoardPage。"""

    def __init__(self, bp):
        self.bp = bp  # BoardPage 引用

    # ── 属性快捷方式 ──

    @property
    def _page(self): return self.bp._page
    @property
    def ai_chat(self): return self.bp.ai_chat
    @property
    def _task_registry(self): return self.bp._task_registry
    @property
    def _runner(self): return self.bp._runner

    # ── 命令分发 ──

    def dispatch(self, cmd: str):
        if cmd == "outline":       return self._cmd_outline()
        elif cmd == "gen_tasks":   return self._cmd_gen_tasks()
        elif cmd == "classify":    return self._cmd_classify()
        elif cmd == "schedule":    return self._cmd_schedule()
        elif cmd == "acceptance":  return self._cmd_acceptance()
        elif cmd == "report":      return self._cmd_report()
        elif cmd == "review":      return self._cmd_review()
        else: Toast.show(self._page, f"未知 AI 命令: {cmd}", "warning")

    # ═══════════════════════════════════════════
    # 通用 AI 动作（右键菜单单任务）
    # ═══════════════════════════════════════════

    def run_ai_action(self, label: str, task_info: dict,
                       action_fn, session_id: str, keep_open: bool = False):
        """通用 AI 动作：打开面板 + 任务卡片 + 后台调用 service 方法 + 结果气泡。"""
        log.debug("ai_action", f"_run_ai_action label={label} session={session_id} "
                  f"ai_chat={'OK' if self.ai_chat else 'NONE'} "
                  f"is_task_running={self.ai_chat.is_task_running if self.ai_chat else 'N/A'}")
        if not self.ai_chat:
            Toast.show(self._page, "AI 面板未就绪", "warning"); return
        if self.ai_chat.is_task_running:
            Toast.show(self._page, "AI 正在处理中，请等待当前任务完成", "warning"); return

        self.bp._open_ai_panel()
        self._runner.setup(label, session_id)

        def _do():
            log.debug("ai_action_bg", f"thread started for {label}")
            cancel = self._runner.get_cancel()
            log.debug("ai_action_bg", f"cancel_event={'OK' if cancel else 'None'}")
            if cancel and cancel.is_set():
                log.debug("ai_action_bg", f"pre-cancelled")
                return  # 取消处理器已更新 UI
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
                    return  # 取消处理器已更新 UI
                if self._runner.get_cancel() and self._runner.get_cancel().is_set():
                    log.debug("ai_action_bg", "cancelled after LLM returned")
                    return  # 取消处理器已更新 UI
                log.debug("ai_action_bg", f"success, adding to _msg_pairs...")
                self.ai_chat._msg_pairs.append(
                    (f"__AI_ONLY__{label}", result, datetime.now()))
                try:
                    if self._page:
                        self._page.run_task(self.bp._rebuild_chat_ui)
                except Exception:
                    pass
                if keep_open:
                    if self._runner.get_cancel() and self._runner.get_cancel().is_set():
                        return
                    active_task_registry.clear()
                    proposed = [t for t in state.get_all_tasks() if t.ai_proposed]
                    tid = task_info.get("id", "")
                    has_ghost = any(t.id == tid and t.ai_proposed for t in proposed)
                    if has_ghost:
                        self.ai_chat.update_task_card("等待确认幽灵卡片…", border_color=theme.warning)
                        self._task_registry.update_status(session_id, "等待确认", 0.8)
                        self.bp._check_ghost_pending_completion()
                        self.bp._start_ghost_polling(session_id, label)
                    else:
                        tid = task_info.get("id", "")
                        results_list = getattr(self.ai_chat, '_proposal_results', []) if self.ai_chat else []
                        already_processed = any(r[0] == tid for r in results_list)
                        if already_processed:
                            log.debug("ai_action_bg", f"ghost already processed by user for {tid}")
                            self._finish_task_card(label, "已完成", theme.success)
                            return
                        log.debug("ai_action_bg", f"keep_open but no ghost card created for {tid}")
                        self._finish_task_card(label, "AI 未创建提案", theme.error)
                else:
                    self._finish_task_card(label, "完成", theme.success)
                log.debug("ai_action_bg", f"done")
            except Exception as ex:
                log.debug("ai_action_bg", f"EXCEPTION: {ex}")
                traceback.print_exc()
                self._finish_task_card(label, f"失败: {ex}", theme.error)

        threading.Thread(target=_do, daemon=True).start()
        log.debug("ai_action", f"thread started")

    # ═══════════════════════════════════════════
    # 1. 生成大纲
    # ═══════════════════════════════════════════

    def _cmd_outline(self):
        if not self._runner.ensure_ready(): return
        self._runner.setup("生成大纲", "outline")

        def _do_outline():
            cancel = self._runner.get_cancel()
            try:
                from app.agent.orchestrator import _load_prompt
                self.ai_chat.update_task_card("正在分析需求...")
                prompt = _load_prompt("generate_outline_interactive.md")
                from app.ui.services.agent_service import AgentService
                result = AgentService.ask(prompt, session_id="outline",
                                        strict=True, cancel_event=cancel)
                if cancel and cancel.is_set():
                    return  # 取消处理器已更新 UI
                self.ai_chat.show_prompt_bubble(result)
                self.ai_chat.update_task_card("请回复上方紫色气泡中的问题...")
                busy_seen = False
                for _ in range(300):
                    if cancel and cancel.is_set():
                        return  # 取消处理器已更新 UI
                    time.sleep(1)
                    if not self.ai_chat: break
                    if self.ai_chat._busy:
                        busy_seen = True
                        self.ai_chat.update_task_card("正在生成大纲...", border_color=theme.warning)
                    elif busy_seen:
                        self._finish_task_card("生成大纲", "完成", theme.success)
                        break
            except Exception as ex:
                self._finish_task_card("生成大纲", f"失败: {ex}", theme.error)

        threading.Thread(target=_do_outline, daemon=True).start()

    # ═══════════════════════════════════════════
    # 2. 生成任务
    # ═══════════════════════════════════════════

    def _cmd_gen_tasks(self):
        if not self._runner.ensure_ready(): return
        self._runner.setup("生成任务", "gen_tasks")

        def _do_gen():
            cancel = self._runner.get_cancel() if self.ai_chat else None
            if cancel is None:
                self.ai_chat.hide_task_card() if self.ai_chat else None
                return
            try:
                from app.agent.orchestrator import _load_prompt
                self.ai_chat.update_task_card("正在分析需求...")
                prompt = _load_prompt("generate_tasks_interactive.md")
                result = AgentService.ask(prompt, session_id="gen_tasks",
                                                         strict=True, cancel_event=cancel)
                if cancel and cancel.is_set():
                    return  # 取消处理器已更新 UI
                self.ai_chat.show_prompt_bubble(result)
                self.ai_chat.update_task_card("请回复上方紫色气泡中的问题...")
                known_before = {t.id for t in state.get_all_tasks()}
                busy_seen = False
                for _ in range(300):
                    if cancel and cancel.is_set():
                        return  # 取消处理器已更新 UI

                    time.sleep(1)
                    if not self.ai_chat: break
                    if self.ai_chat._busy:
                        busy_seen = True
                        self.ai_chat.update_task_card("正在生成任务...", border_color=theme.warning)
                    elif busy_seen:
                        new_tasks = [t for t in state.get_all_tasks()
                                      if t.ai_proposed and t.id not in known_before]
                        if new_tasks:
                            self.bp._refresh_board()
                            self.bp._poll_ghost_resolution("生成任务", {t.id for t in new_tasks}, cancel)
                        else:
                            self._finish_task_card("生成任务", "完成（无幽灵任务）", theme.success)
                        break
            except Exception as ex:
                traceback.print_exc()
                try:
                    self._finish_task_card("生成任务", f"失败: {ex}", theme.error)
                except Exception:
                    self.ai_chat.hide_task_card() if self.ai_chat else None

        threading.Thread(target=_do_gen, daemon=True).start()

    # ═══════════════════════════════════════════
    # 3-5. 批量分类/排程/验收
    # ═══════════════════════════════════════════

    _CMD_PROMPTS = {
        "gen_tasks": "...",
        "classify": (
            "检查所有待处理（backlog）任务，根据航空维修优先级规则为每个任务分配优先级。"
            "使用 classify_task 工具将每个待处理任务移至已分类列。"
        ),
        "schedule": (
            "检查所有已分类（triage）任务，为每个任务排程。"
            "使用 search_employees 查找合适的员工，使用 schedule_task 工具排程。"
        ),
        "acceptance": (
            "以零容忍标准审核所有验收中（inspection）任务。默认判决：驳回。"
            "对每个任务调用 acceptance_review 工具。"
        ),
    }

    def _cmd_classify(self):
        log.debug("classify", "_cmd_classify called")
        if not self._runner.ensure_ready(): return
        backlog = [t for t in state.get_all_tasks() if t.status.value == "backlog"]
        log.debug("classify", f"backlog count={len(backlog)}")
        if not backlog:
            self.bp._open_ai_panel()
            self.bp._show_ai_in_panel("自动分类", "待处理列中没有任务需要分类。")
            return
        tasks_str = "\n".join(
            f"- [{t.id}] {t.title} (ATA {t.ata_chapter or '未指定'}, 飞机 {t.aircraft_reg or '未指定'})"
            for t in backlog
        )
        self._runner.setup("自动分类", "classify", initial_status=f"正在分析 {len(backlog)} 个任务...")
        self.ai_chat.update_task_card(f"正在分析 {len(backlog)} 个任务...")

        def _do():
            log.debug("classify", "_do thread started")
            cancel = self._runner.get_cancel()
            log.debug("classify", f"cancel_event={cancel}")
            try:
                from app.ui.services.agent_service import AgentService
                prompt = (f"{self._CMD_PROMPTS['classify']}\n\n"
                          f"待处理任务:\n{tasks_str}\n\n使用 classify_task 逐个分类。")
                self.ai_chat.update_task_card("正在执行分类...", border_color=theme.warning)
                for bt in backlog:
                    if bt.ai_proposed:
                        state.update_task(bt.id, ai_proposed=False, ai_priority=None)
                pending_before = {t.id for t in state.get_all_tasks() if t.ai_proposed}
                log.debug("classify", f"before ask, pending_before={len(pending_before)}")
                result = AgentService.ask(prompt, session_id="classify",
                                                         cancel_event=cancel)
                log.debug("classify", f"ask done, result_len={len(result) if result else 0}")
                if cancel and cancel.is_set():
                    self._finish_task_card("自动分类", "已取消", theme.text_disabled)
                    return
                self.bp._refresh_board()
                self.bp._rebuild_chat_ui_sync()
                if cancel and cancel.is_set(): return
                pending_after = {t.id for t in state.get_all_tasks() if t.ai_proposed}
                pending = pending_after - pending_before
                if pending:
                    self.bp._poll_ghost_resolution("自动分类", pending, cancel)
                else:
                    registry_status = next((t.get("status") for t in self._task_registry.get_all() if t["id"] == "classify"), None)
                    if registry_status and registry_status not in ("准备中...", "分析中..."):
                        return
                    self._finish_task_card("自动分类", "完成（无幽灵卡）", theme.success)
            except Exception as ex:
                self._finish_task_card("自动分类", f"失败: {ex}", theme.error)

        log.debug("classify", "starting thread")
        threading.Thread(target=_do, daemon=True).start()
        log.debug("classify", "thread started")

    def _cmd_schedule(self):
        if not self._runner.ensure_ready(): return
        triage = [t for t in state.get_all_tasks() if t.status.value == "triage"]
        if not triage:
            self.bp._open_ai_panel()
            self.bp._show_ai_in_panel("自动排程", "已分类列中没有任务需要排程。")
            return
        tasks_str = "\n".join(
            f"- [{t.id}] {t.title} (优先级: {t.priority.value}, ATA {t.ata_chapter or '未指定'})"
            for t in triage
        )
        self._runner.setup("自动排程", "schedule", initial_status=f"正在分析 {len(triage)} 个任务...")
        self.ai_chat.update_task_card(f"正在分析 {len(triage)} 个任务...")

        def _do():
            cancel = self._runner.get_cancel()
            try:
                from app.ui.services.agent_service import AgentService
                prompt = (f"{self._CMD_PROMPTS['schedule']}\n\n"
                          f"已分类任务:\n{tasks_str}\n\n使用 search_employees + schedule_task 逐个排程。")
                self.ai_chat.update_task_card("正在执行排程...", border_color=theme.warning)
                for tt in triage:
                    if tt.ai_proposed:
                        state.update_task(tt.id, ai_proposed=False)
                pending_before = {t.id for t in state.get_all_tasks() if t.ai_proposed}
                result = AgentService.ask(prompt, session_id="schedule",
                                                         cancel_event=cancel)
                if cancel and cancel.is_set():
                    self._finish_task_card("自动排程", "已取消", theme.text_disabled)
                    return
                self.bp._refresh_board()
                self.bp._rebuild_chat_ui_sync()
                if cancel and cancel.is_set(): return
                pending_after = {t.id for t in state.get_all_tasks() if t.ai_proposed}
                pending = pending_after - pending_before
                if pending:
                    self.bp._poll_ghost_resolution("自动排程", pending, cancel)
                else:
                    registry_status = next((t.get("status") for t in self._task_registry.get_all() if t["id"] == "schedule"), None)
                    if registry_status and registry_status not in ("准备中...", "分析中..."):
                        return
                    self._finish_task_card("自动排程", "完成（无幽灵卡）", theme.success)
            except Exception as ex:
                self._finish_task_card("自动排程", f"失败: {ex}", theme.error)

        threading.Thread(target=_do, daemon=True).start()

    def _cmd_acceptance(self):
        log.debug("acceptance", "===== _cmd_acceptance called =====")
        if not self._runner.ensure_ready(): return
        insp = [t for t in state.get_all_tasks() if t.status.value == "inspection"]
        log.debug("acceptance", f"inspection tasks found: {len(insp)}")
        if not insp:
            self.bp._open_ai_panel()
            self.bp._show_ai_in_panel("自动验收", "验收列中没有任务。")
            return
        tasks_str = "\n".join(
            f"- [{t.id}] {t.title} (负责人: {t.employee_name or '未指定'})"
            for t in insp
        )
        self._runner.setup("自动验收", "acceptance", initial_status=f"正在审核 {len(insp)} 个任务...")
        self.ai_chat.update_task_card(f"正在审核 {len(insp)} 个任务...")

        def _do():
            cancel = self._runner.get_cancel()
            log.debug("acceptance", f"_do thread started, cancel_event={cancel}")
            try:
                from app.ui.services.agent_service import AgentService
                prompt = (f"{self._CMD_PROMPTS['acceptance']}\n\n"
                          f"验收任务:\n{tasks_str}\n\n"
                          f"对每个验收中任务，必须调用 acceptance_review 工具提交审核建议。")
                log.debug("acceptance", f"prompt length={len(prompt)}")
                self.ai_chat.update_task_card("正在审核提交日志...", border_color=theme.warning)
                for t in insp:
                    if t.ai_proposed:
                        state.update_task(t.id, ai_proposed=False,
                                          ai_acceptance_recommendation=None,
                                          ai_acceptance_reason=None)
                        log.debug("acceptance", f"cleared stale ai_proposed for {t.id}")
                pending_before = {t.id for t in state.get_all_tasks() if t.ai_proposed}
                log.debug("acceptance", f"pending_before={len(pending_before)}: {pending_before}")
                log.debug("acceptance", f"calling AgentService.ask()...")
                result = AgentService.ask(prompt, session_id="acceptance",
                                                         cancel_event=cancel)
                log.debug("acceptance", f"AgentService.ask() returned, len={len(result) if result else 0}")
                if cancel and cancel.is_set():
                    log.debug("acceptance", "cancelled after ask")
                    self._finish_task_card("自动验收", "已取消", theme.text_disabled)
                    return
                self.bp._refresh_board()
                log.debug("acceptance", "_refresh_board() done")
                self.bp._show_ai_in_panel("自动验收", result)
                if cancel and cancel.is_set(): return
                pending_after = {t.id for t in state.get_all_tasks() if t.ai_proposed}
                log.debug("acceptance", f"pending_after={len(pending_after)}: {pending_after}")
                pending = pending_after - pending_before
                log.debug("acceptance", f"new pending ghosts={len(pending)}: {pending}")
                if pending:
                    log.debug("acceptance", "entering _poll_ghost_resolution...")
                    self.bp._poll_ghost_resolution("自动验收", pending, cancel)
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
    # 6. 生成报表
    # ═══════════════════════════════════════════

    def _cmd_report(self):
        self._task_registry.register("report", "生成报表", "准备中...", "report")
        self.bp._cmd_report_show_result(None)

    # ═══════════════════════════════════════════
    # 7. 任务审核
    # ═══════════════════════════════════════════

    def _cmd_review(self):
        self._task_registry.register("review", "任务审核", "准备中...", "review")
        self.bp._cmd_review_show_result(None)

    # ── 内部辅助 ──

    def _finish_task_card(self, label: str, status: str, color: str):
        """委托给 BoardPage._finish_task_card。"""
        self.bp._finish_task_card(label, status, color)
