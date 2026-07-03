"""看板主页面."""

from datetime import datetime, timedelta

import flet as ft

from app.config.theme import theme, s
from app.core.models.aircraft import Aircraft, AircraftStatus
from app.core.models.kanban import FilterState
from app.core.models.task import Priority
from app.core.services.board_service import board_service
from app.core.services.task_service import task_service
from app.core.state import state
from app.ui.components.ai_suggestion import FleetStatusBar
from app.ui.components.command_bar import CommandBar
from app.ui.components.kanban_board import KanbanBoard
from app.ui.components.side_panel import SidePanel
from app.ui.components.ai_chat import AIChatPanel
from app.ui.widgets.toast import Toast


class BoardPage:
    def __init__(self, api_ready: bool = False):
        self.api_ready = api_ready
        self.kanban_board: KanbanBoard | None = None
        self.side_panel: SidePanel | None = None
        self.ai_chat: AIChatPanel | None = None
        self.command_bar: CommandBar | None = None
        self.fleet_status: FleetStatusBar | None = None
        self._page: ft.Page | None = None
        self._search_field: ft.TextField | None = None
        self._search_box: ft.Container | None = None
        self._drag_start_width: float | None = None
        self._drag_start_x: float | None = None
        self._agent_busy = False
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
            ], spacing=0, expand=True),
            expand=True, bgcolor=theme.bg,
        )
        self._fill_board_from_state()
        return main

    # ═══════════════════════ 数据 ═══════════════════════

    def _fill_board_from_state(self):
        if not self.kanban_board: return
        bs = board_service.get_board()
        tasks_map = {}
        ai_proposed = {}
        for ids in bs.tasks.values():
            for tid in ids:
                t = state.get_task(tid)
                if not t: continue
                if t.ai_proposed:
                    ai_proposed[tid] = t
                else:
                    tasks_map[tid] = t
        self.kanban_board.render_board(bs, tasks_map, do_update=False)
        self._render_ai_ghost_cards(ai_proposed)
        s = board_service.get_fleet_summary()
        if self.fleet_status: self.fleet_status._build(s)

    def _render_ai_ghost_cards(self, ai_tasks: dict):
        """将 AI 建议的任务渲染为幽灵卡片（注入目标列预览，拒绝则退回源列）。"""
        from app.ui.widgets.ai_ghost_card import AIGhostCard, AIProposal, GhostCardManager
        if not hasattr(self, '_ghost_mgr'):
            self._ghost_mgr = GhostCardManager()

        for col in self.kanban_board._columns.values():
            if not hasattr(col, 'card_list') or not col.card_list:
                continue
            to_remove = [c for c in col.card_list.controls
                          if isinstance(c, AIGhostCard)]
            for c in to_remove:
                col.card_list.controls.remove(c)

        for tid, t in ai_tasks.items():
            schedule_data = {}
            for sug in (t.ai_suggestions or []):
                if isinstance(sug, dict) and sug.get("proposal_type") == "schedule":
                    schedule_data = sug
                    break

            if t.ai_priority:
                prop_type = "classify"
                display_priority = t.ai_priority.value
                render_column = "triage"
                source_column = "backlog"
            elif schedule_data:
                prop_type = "schedule"
                display_priority = t.priority.value
                render_column = "scheduled"
                source_column = "triage"
            else:
                prop_type = "new_task"
                display_priority = t.priority.value
                render_column = t.status.value
                source_column = render_column

            if render_column not in self.kanban_board._columns:
                continue
            col = self.kanban_board._columns[render_column]
            if not hasattr(col, 'card_list') or not col.card_list:
                continue

            task_data = {
                "id": tid, "title": t.title, "description": t.description,
                "ata_chapter": t.ata_chapter, "aircraft_reg": t.aircraft_reg,
                "priority": display_priority, "task_type": t.task_type.value,
                "zone": t.zone, "estimated_hours": float(schedule_data.get("estimated_hours", t.estimated_hours)),
            }
            if schedule_data:
                for k in ("planned_start", "planned_end", "employee_id", "employee_name"):
                    if schedule_data.get(k):
                        task_data[k] = schedule_data[k]

            proposal = AIProposal(
                id=f"ai_{tid}",
                proposal_type=prop_type,
                task_data=task_data,
                source_column=source_column,
                target_column=render_column,
            )
            ghost = AIGhostCard(
                proposal,
                on_accept=lambda p, tid=tid: self._accept_ai_task(tid),
                on_reject=lambda p, tid=tid: self._reject_ai_task(tid),
            )
            col.card_list.controls.insert(0, ghost)
        if ai_tasks:
            try:
                self.kanban_board.column_row.update()
                self.kanban_board.update()
            except Exception:
                pass

    def _accept_ai_task(self, tid):
        """接受 AI 建议任务——业务变更由 AIGhostCard 执行，此处仅清理标记。"""
        t = state.get_task(tid)
        if not t:
            return
        ai_suggestions = [s for s in (t.ai_suggestions or [])
                          if not (isinstance(s, dict) and
                                  s.get("proposal_type") in ("schedule",))]
        state.update_task(tid, ai_proposed=False, ai_priority=None,
                          ai_suggestions=ai_suggestions)
        from app.ui.widgets.toast import Toast
        Toast.show(self._page, "AI 建议已接受", "success")
        self._refresh_board()

    def _reject_ai_task(self, tid):
        """拒绝 AI 建议任务——分类/排程提案仅清除标记，新建提案则删除任务。"""
        t = state.get_task(tid)
        if not t:
            return
        is_modify = t.ai_priority or any(
            isinstance(s, dict) and s.get("proposal_type") in ("schedule",)
            for s in (t.ai_suggestions or [])
        )
        if is_modify:
            ai_suggestions = [s for s in (t.ai_suggestions or [])
                              if not (isinstance(s, dict) and
                                      s.get("proposal_type") in ("schedule",))]
            state.update_task(tid, ai_proposed=False, ai_priority=None,
                              ai_suggestions=ai_suggestions)
        else:
            state.delete_task(tid)
        from app.ui.widgets.toast import Toast
        Toast.show(self._page, "AI 建议已拒绝", "info")
        self._refresh_board()

    def load_demo_data(self):
        demo_aircraft = [
            Aircraft(registration="B-5823", model="737-800", msn="39999",
                     status=AircraftStatus.IN_MAINTENANCE, total_hours=28500,
                     current_location="Hangar 3", open_defects=3, overdue_tasks_count=1),
            Aircraft(registration="B-2518", model="A320neo", msn="8876",
                     status=AircraftStatus.OPERATIONAL, total_hours=12400,
                     current_location="Gate A12"),
            Aircraft(registration="B-9076", model="A330-300", msn="1503",
                     status=AircraftStatus.AOG, total_hours=32100,
                     current_location="Hangar 1", open_defects=1),
        ]
        for ac in demo_aircraft: state.add_aircraft(ac)

        now = datetime.now()
        demo_tasks = [
            ("backlog", "APU 启动时间超限检查", "B-5823", "49-11-01", "aog", "inspection", "张", 3.0, "310"),
            ("backlog", "右发滑油消耗率偏高", "B-9076", "79-21-01", "aog", "troubleshoot", "李", 5.0, "420"),
            ("backlog", "客舱空调出风口异响", "B-2518", "21-51-01", "cat_c", "troubleshoot", "王", 2.0, "510"),
            ("triage", "前起落架转向异响排查", "B-5823", "32-41-03", "cat_a", "troubleshoot", "张", 4.5, "710"),
            ("triage", "左发 N1 振动指示异常", "B-9076", "77-11-01", "cat_b", "troubleshoot", "赵", 6.0, "420"),
            ("scheduled", "A 检 — 飞行控制面功能检查", "B-5823", "27-10-00", "cat_b", "inspection", "李", 8.0, "210"),
            ("scheduled", "发动机滑油更换", "B-2518", "79-00-01", "cat_c", "servicing", "王", 2.0, "420"),
            ("ready", "机翼前缘防冰管路测试", "B-5823", "30-11-01", "cat_c", "test", "张", 4.0, "610"),
            ("ready", "APU 滑油勤务", "B-5823", "49-91-01", "cat_c", "servicing", "赵", 1.5, "310"),
            ("in_progress", "起落架收放功能测试", "B-5823", "32-31-01", "cat_b", "test", "张", 3.0, "710"),
            ("in_progress", "右发燃油滤更换", "B-9076", "73-11-03", "cat_a", "removal_install", "李", 4.0, "420"),
            # ── 验收中任务（不同质量等级，测试 AI 审核智能程度）──
            ("inspection", "C 检 — 机身结构详细检查", "B-5823", "53-10-01", "cat_c", "inspection", "王", 48.0, "100"),
            ("inspection", "右发 N1 振动传感器更换", "B-9076", "77-11-01", "cat_a", "removal_install", "李", 2.5, "420"),
            ("inspection", "左大翼前缘凹坑修理", "B-5823", "57-40-01", "cat_b", "repair", "赵", 12.0, "610"),
            ("inspection", "客舱应急灯光系统检查", "B-2518", "33-51-01", "cat_c", "inspection", "张", 1.5, "510"),
            ("parts_hold", "左发点火电嘴更换", "B-9076", "74-11-03", "cat_a", "removal_install", "赵", 3.0, "420"),
            ("completed", "驾驶舱仪表灯光检查", "B-2518", "33-11-01", "cat_d", "inspection", "李", 1.0, "110"),
            ("completed", "APU 进气门清洁", "B-5823", "49-11-01", "cat_d", "servicing", "张", 2.0, "310"),
        ]
        status_order = ["backlog", "triage", "scheduled", "ready",
                        "in_progress", "inspection", "parts_hold", "completed"]
        # 各目标列的正确路径（跳过不经过的中间状态）
        _TARGET_PATHS = {
            "backlog": [],
            "triage": ["triage"],
            "scheduled": ["triage", "scheduled"],
            "ready": ["triage", "scheduled", "ready"],
            "in_progress": ["triage", "scheduled", "ready", "in_progress"],
            "inspection": ["triage", "scheduled", "ready", "in_progress", "inspection"],
            "parts_hold": ["triage", "scheduled", "ready", "in_progress", "parts_hold"],
            "completed": ["triage", "scheduled", "ready", "in_progress", "completed"],
        }
        # 员工映射：姓名 → (ID, 姓名)
        _EMP_MAP = {"张": ("ZH001", "张工"), "李": ("ZH002", "李工"),
                     "王": ("ZH003", "王工"), "赵": ("ZH004", "赵工")}
        due_map = {"aog": 4, "cat_a": 24, "cat_b": 72, "cat_c": 168, "cat_d": 720}
        for col_target, title, reg, ata, pri, ttype, who, hrs, zone in demo_tasks:
            eid, ename = _EMP_MAP.get(who, ("", who))
            task = task_service.create_task(
                title=title, description=f"{title}。ATA {ata}，飞机 {reg}。",
                aircraft_reg=reg, ata_chapter=ata, priority=pri, task_type=ttype,
                assignee=who, employee_id=eid, employee_name=ename,
                estimated_hours=hrs, zone=zone,
                due_date=now + timedelta(hours=due_map.get(pri, 72)),
            )
            if not task: continue
            path = _TARGET_PATHS.get(col_target, [])
            for mid in path:
                try:
                    if mid == "parts_hold":
                        task_service.update_task(task.id, parts_available=False,
                                                 parts_required=["PN-REQUIRED"])
                    task_service.move_task(task.id, mid, changed_by="demo")
                except Exception as ex:
                    print(f"[DEMO] move failed: {title} → {mid}: {ex}")
            # 已排程及之后的任务补充计划时间
            if col_target in ("scheduled", "ready", "in_progress", "inspection",
                              "parts_hold", "completed"):
                ps = now - timedelta(hours=hrs * 2)
                pe = now + timedelta(hours=hrs)
                task_service.update_task(task.id, planned_start=ps, planned_end=pe)
            print(f"[DEMO] created: {title} → {col_target} (status={task.status.value})")

        # ── 补充交接班日志（不同质量等级，测试 AI 审核智能程度）──
        _LOGS = {
            # ✅ 详细日志 → AI 应建议同意
            "C 检 — 机身结构详细检查": (
                "【工作内容】按 C 检工卡完成机身结构详细检查。\n"
                "【检查范围】前机身 (STA 178-360)、中机身 (STA 360-727)、后机身 (STA 727-947)。\n"
                "【检查方法】目视检查 + 涡流探伤 (ET) 关键紧固件孔。\n"
                "【发现问题】STA 420 处长桁有一处 3mm 腐蚀坑，已按 SRM 53-00-01 打磨处理，"
                "剩余壁厚 1.27mm > 1.02mm 容差。\n"
                "【测量值】腐蚀坑深度 0.3mm，打磨区域 15×20mm，NDT 确认无裂纹。\n"
                "【工卡签署】全部 48 项检查已完成并签署。\n"
                "【工具清点】已清点，无遗漏。\n"
                "【备注】建议下次 C 检复查 STA 420 区域。"
            ),
            # ⚠ 日志太简略 → AI 应建议需要更多信息
            "右发 N1 振动传感器更换": (
                "更换右发 N1 振动传感器，测试正常。"
            ),
            # ⚠ RII 项目 + 详细日志 → AI 应提示 RII 需检查员签署
            "左大翼前缘凹坑修理": (
                "【工作内容】左大翼前缘 STA 580 处凹坑修理。\n"
                "【修理方法】按 SRM 57-40-01 执行外修补贴片修理。\n"
                "【材料】2024-T3 铝板 0.063\"，Hi-Lok HL18-6 紧固件 × 8。\n"
                "【NDT】修理前后涡流探伤，无裂纹。\n"
                "【气动外形】修理后外形在 AMM 容差范围内。"
                "【备注】RII 项目，待检查员最终签署。"
            ),
            # ❌ 无日志 → AI 应建议驳回
            "客舱应急灯光系统检查": "",
        }
        _RII_TASKS = {"左大翼前缘凹坑修理"}  # RII 必检项目
        log_count = 0
        for t in state.get_all_tasks():
            if t.title in _LOGS:
                sh_log = _LOGS[t.title]
                is_rii = t.title in _RII_TASKS
                updates = {}
                if sh_log:
                    updates["shift_handover_log"] = sh_log
                if is_rii:
                    updates["is_rii"] = True
                    updates["inspector"] = "刘"  # RII 检查员
                if updates:
                    task_service.update_task(t.id, **updates)
                    log_count += 1
                    print(f"[DEMO] handover log set: {t.title} (rii={is_rii})")
        print(f"[DEMO] handover logs applied: {log_count} tasks, inspection count: {sum(1 for t in state.get_all_tasks() if t.status.value == 'inspection')}")

    # ═══════════════════════ 事件 ═══════════════════════

    def _on_state_changed(self): self._refresh_board()

    def _refresh_board(self):
        if not self.kanban_board: return
        bs = board_service.get_board()
        tasks_map = {}
        ai_proposed = {}
        for ids in bs.tasks.values():
            for tid in ids:
                t = state.get_task(tid)
                if not t: continue
                if t.ai_proposed:
                    ai_proposed[tid] = t
                else:
                    tasks_map[tid] = t
        self.kanban_board.render_board(bs, tasks_map)
        self._render_ai_ghost_cards(ai_proposed)
        self.fleet_status.update_summary(board_service.get_fleet_summary())

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
        import time
        self.ai_chat.update_task_card(status, border_color=color)
        self.ai_chat.show_status_bubble(f"{label} {status}", color)
        time.sleep(2)
        self.ai_chat.hide_task_card()

    def _poll_ghost_resolution(self, label: str, pending_ids: set,
                                cancel_event, timeout: int = 300):
        """轮询等待幽灵任务全部确认/拒绝。cancel_event 由调用方传入。"""
        import time
        cancel = cancel_event
        if cancel is None:
            self.ai_chat.hide_task_card() if self.ai_chat else None
            return
        for i in range(timeout):
            if cancel.is_set():
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
                self._refresh_board()
        self._finish_task_card(label, "等待超时", theme.text_disabled)

    def _on_side_panel_close(self):
        if self._page: self._page.update()

    def _on_edit_task(self, task):
        """从侧边栏编辑按钮触发的编辑弹窗。"""
        self._dlg_edit(task)

    def _on_card_context_menu(self, tid, e):
        from app.ui.widgets.context_menu import ContextMenu
        t = state.get_task(tid)
        submit_label = "提交验收" if t and t.status.value == "in_progress" else (
            "验收中" if t and t.status.value == "inspection" else (
            "已完成" if t and t.status.value == "completed" else "提交任务"))
        ContextMenu(
            items=[
                {"label": "编辑", "icon": ft.Icons.EDIT_OUTLINED, "action": "edit"},
                {"label": "分配...", "icon": ft.Icons.PERSON_ADD, "action": "assign"},
                {"label": submit_label, "icon": ft.Icons.CHECK_CIRCLE_OUTLINE,
                 "action": "submit",
                 "color": theme.success if t and t.status.value != "completed"
                 else theme.text_disabled},
                {"divider": True},
                {"label": "AI 解释任务", "icon": ft.Icons.PSYCHOLOGY_OUTLINED,
                 "action": "ai_explain"},
                {"label": "AI 查找相关文档", "icon": ft.Icons.SEARCH,
                 "action": "search"},
                {"divider": True},
                {"label": "删除", "icon": ft.Icons.DELETE_OUTLINE,
                 "color": theme.error, "action": "delete"},
            ],
            on_select=lambda a: self._card_action(tid, a),
        ).show(self._page)

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

    def _dlg_priority(self, tid, col, index):
        """backlog → triage：补充优先级。"""
        ff = theme.font_family
        options = [
            ("aog", "AOG", "立即排故", theme.priority_aog),
            ("cat_a", "Cat A", "当日完成", theme.priority_cat_a),
            ("cat_b", "Cat B", "72 小时内", theme.priority_cat_b),
            ("cat_c", "Cat C", "10 天内", theme.priority_cat_c),
            ("cat_d", "Cat D", "120 天内", theme.priority_cat_d),
        ]
        selected = {"val": "cat_c"}

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
                sel = options[i][0] == v
                color = options[i][3]
                chip.border = ft.border.all(
                    1.5, color if sel else theme.border)
                chip.bgcolor = ft.Colors.with_opacity(
                    0.06, color) if sel else theme.card
                row = chip.content.controls[0]
                row.controls[1].color = color if sel else theme.text_primary
                chip.update()

        def _confirm(_):
            priority = selected["val"]
            try:
                from app.core.models.task import Priority
                task_service.move_task(tid, col, index=index)
                task_service.update_task(tid, priority=Priority(priority))
                Toast.show(self._page, f"已分类 — {options[[o[0] for o in options].index(priority)][1]}", "success")
            except Exception as e:
                Toast.show(self._page, str(e), "warning")
            dlg.close()

        from app.ui.components.modal_dialog import ModalDialog

        header = ft.Container(
            ft.Row([
                ft.Icon(ft.Icons.FLAG_OUTLINED, size=s(15), color="#5294e2"),
                ft.Text("确认优先级", size=s(14),
                        weight=ft.FontWeight.W_600,
                        color=theme.text_primary, font_family=ff),
                ft.Container(expand=True),
                ft.IconButton(ft.Icons.CLOSE, icon_size=s(16),
                              icon_color=theme.text_secondary,
                              style=ft.ButtonStyle(
                                  bgcolor=ft.Colors.TRANSPARENT,
                                  overlay_color=ft.Colors.RED_900,
                                  shape=ft.RoundedRectangleBorder(radius=s(4))),
                              on_click=lambda e: dlg.close()),
            ], spacing=s(8)),
            padding=ft.padding.only(
                left=s(14), top=s(8), right=s(6), bottom=s(8)),
            border=ft.border.only(
                bottom=ft.BorderSide(1, theme.border)),
        )

        form = ft.Container(
            ft.Column([
                ft.Row(chips[:3], spacing=s(8),
                       alignment=ft.MainAxisAlignment.CENTER),
                ft.Row(chips[3:], spacing=s(8),
                       alignment=ft.MainAxisAlignment.CENTER),
            ], spacing=s(8), tight=True),
            padding=ft.padding.all(s(14)),
        )

        btn_style = ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=s(6)),
            padding=ft.padding.only(
                left=s(18), top=s(7), right=s(18), bottom=s(7)),
            text_style=ft.TextStyle(size=s(12), font_family=ff),
        )
        footer = ft.Container(
            ft.Row([
                ft.Container(expand=True),
                ft.OutlinedButton("取消", on_click=lambda e: dlg.close(),
                    style=ft.ButtonStyle(
                        shape=btn_style.shape, padding=btn_style.padding,
                        text_style=btn_style.text_style,
                        side=ft.BorderSide(1, theme.border),
                        color=theme.text_secondary)),
                ft.ElevatedButton("确认", on_click=_confirm,
                    style=ft.ButtonStyle(
                        shape=btn_style.shape, padding=btn_style.padding,
                        text_style=btn_style.text_style,
                        bgcolor="#5294e2", color=ft.Colors.WHITE,
                        elevation=0)),
            ], spacing=s(8)),
            padding=ft.padding.only(
                left=s(14), top=s(8), right=s(14), bottom=s(10)),
            border=ft.border.only(
                top=ft.BorderSide(1, theme.border)),
        )

        content = ft.Column([header, form, footer], spacing=0, tight=True)
        dlg = ModalDialog(self._page, content, width=540)
        dlg.open()

    def _dlg_schedule(self, tid, col, index):
        """triage → scheduled：补充时间、工时和人员。"""
        ff = theme.font_family

        def _field(hint="", width=None):
            return ft.TextField(
                hint_text=hint, border_color=theme.border,
                focused_border_color=theme.info, cursor_color=theme.info,
                text_style=ft.TextStyle(color="#e0e0e0", size=s(12), font_family=ff),
                hint_style=ft.TextStyle(color=theme.text_secondary, size=s(11), font_family=ff),
                bgcolor=theme.card, dense=True, border_radius=s(6),
                content_padding=ft.padding.only(left=s(10), top=s(8), right=s(10), bottom=s(8)),
                width=width)

        def _label(text, required=False):
            if required:
                return ft.Text(spans=[
                    ft.TextSpan(text, ft.TextStyle(color=theme.text_primary, size=s(11), font_family=ff, weight=ft.FontWeight.W_500)),
                    ft.TextSpan(" *", ft.TextStyle(color=theme.error, size=s(11), font_family=ff, weight=ft.FontWeight.W_500))])
            return ft.Text(text, size=s(11), color=theme.text_primary, font_family=ff, weight=ft.FontWeight.W_500)

        def _col(lbl, ctrl):
            return ft.Column([lbl, ctrl], spacing=s(4), tight=True, expand=True)

        hours_f = _field("计划工时 (h)，如 4.5", width=220)
        assignee_id_f = _field("员工 ID，如 ZH001")
        assignee_name_f = _field("姓名，如 张工")
        start_hour_f = _field("08", width=s(62))
        start_min_f = _field("30", width=s(62))
        due_hour_f = _field("08", width=s(62))
        due_min_f = _field("30", width=s(62))

        # ── 输入校验 ──
        def _clamp_tf(tf, hi):
            val = (tf.value or "").strip()
            if val:
                if not val.isdigit(): tf.value = ""; tf.update(); return
                n = int(val)
                if n > hi: tf.value = str(hi); tf.update()
        for _tf, _hi in [(start_hour_f, 23), (start_min_f, 59),
                          (due_hour_f, 23), (due_min_f, 59)]:
            _tf.on_blur = lambda e, t=_tf, h=_hi: _clamp_tf(t, h)

        def _make_date_picker(initial_date=None):
            from datetime import datetime as dt
            state = {"date": initial_date}
            dp = ft.DatePicker(first_date=dt(2024,1,1), last_date=dt(2030,12,31),
                on_change=lambda e: _on_pick(e))
            if initial_date:
                display = ft.Text(initial_date.strftime("%Y-%m-%d"), size=s(12), color="#e0e0e0", font_family=ff)
            else:
                display = ft.Text("点击选择日期", size=s(12), color=theme.text_secondary, font_family=ff)
            ctrl = ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.CALENDAR_TODAY_OUTLINED, size=s(14), color=theme.text_secondary),
                    display,
                ], spacing=s(6)),
                bgcolor=theme.card, border_radius=s(6),
                border=ft.border.all(1, theme.border),
                padding=ft.padding.only(left=s(10), top=s(8), right=s(10), bottom=s(8)),
                on_click=lambda e: self._page.open(dp), ink=True)
            def _on_pick(e):
                if e.control.value: state["date"]=e.control.value; display.value=state["date"].strftime("%Y-%m-%d"); display.color="#e0e0e0"; ctrl.update(); _recalc()
            def _set_err(msg): display.value=msg; display.color=theme.error; ctrl.border=ft.border.all(1,theme.error); ctrl.update()
            def _clear_err():
                if state["date"]: display.value=state["date"].strftime("%Y-%m-%d"); display.color="#e0e0e0"
                else: display.value="点击选择日期"; display.color=theme.text_secondary
                ctrl.border=ft.border.all(1,theme.border); ctrl.update()
            return ctrl, state, _set_err, _clear_err

        # ── 预填任务已有的计划时间/人员 ──
        t = state.get_task(tid)
        start_date_ctrl, start_date_state, start_date_err, start_date_clr = _make_date_picker(
            initial_date=t.planned_start if t else None)
        due_date_ctrl, due_date_state, due_date_err, due_date_clr = _make_date_picker(
            initial_date=t.planned_end if t else None)
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
            d = date_state["date"]
            if not d: return None
            from datetime import datetime as dt
            h = (h_f.value or "").strip()
            m = (m_f.value or "").strip()
            if h and m:
                try: return dt(d.year, d.month, d.day, int(h), int(m))
                except: pass
            return d

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
                task_service.move_task(tid, col, index=index)
                updates = {"assignee": f"{aid} {aname}"}
                try: updates["estimated_hours"] = float(hs)
                except: pass
                updates["due_date"] = due_dt
                task_service.update_task(tid, **updates)
                Toast.show(self._page, "已排程", "success")
            except Exception as ex: Toast.show(self._page, str(ex), "warning")
            dlg.close()

        from app.ui.components.modal_dialog import ModalDialog
        header=ft.Container(
            ft.Row([ft.Icon(ft.Icons.CALENDAR_MONTH_OUTLINED,size=s(15),color="#5294e2"),
                ft.Text("排程信息",size=s(14),weight=ft.FontWeight.W_600,color=theme.text_primary,font_family=ff),
                ft.Container(expand=True),
                ft.IconButton(ft.Icons.CLOSE,icon_size=s(16),icon_color=theme.text_secondary,
                    style=ft.ButtonStyle(bgcolor=ft.Colors.TRANSPARENT,
                        overlay_color=ft.Colors.RED_900,
                        shape=ft.RoundedRectangleBorder(radius=s(4))),
                    on_click=lambda e: dlg.close())],spacing=s(8)),
            padding=ft.padding.only(left=s(14),top=s(8),right=s(6),bottom=s(8)),
            border=ft.border.only(bottom=ft.BorderSide(1,theme.border)))
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
        bs=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=s(6)),
            padding=ft.padding.only(left=s(18),top=s(7),right=s(18),bottom=s(7)),
            text_style=ft.TextStyle(size=s(12),font_family=ff))
        footer=ft.Container(
            ft.Row([ft.Container(expand=True),
                ft.OutlinedButton("取消",on_click=lambda e: dlg.close(),
                    style=ft.ButtonStyle(shape=bs.shape,padding=bs.padding,text_style=bs.text_style,
                        side=ft.BorderSide(1,theme.border),color=theme.text_secondary)),
                ft.ElevatedButton("确认排程",on_click=_confirm,
                    style=ft.ButtonStyle(shape=bs.shape,padding=bs.padding,text_style=bs.text_style,
                        bgcolor="#5294e2",color=ft.Colors.WHITE,elevation=0))],spacing=s(8)),
            padding=ft.padding.only(left=s(14),top=s(8),right=s(14),bottom=s(10)),
            border=ft.border.only(top=ft.BorderSide(1,theme.border)))
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
        if not self.ai_chat:
            Toast.show(self._page, "AI 面板未就绪", "warning"); return
        if self.ai_chat.is_task_running:
            Toast.show(self._page, "AI 正在处理中，请等待当前任务完成", "warning"); return
        self._open_ai_panel()
        self.ai_chat.show_task_card("生成大纲")

        import threading, time

        def _do_outline():
            cancel = self.ai_chat._cancel_event
            try:
                from app.ui.services.agent_service import AgentService
                from app.agent.orchestrator import _load_prompt
                self.ai_chat.update_task_card("正在分析需求...")
                prompt = _load_prompt("generate_outline_interactive.md")
                result = AgentService.ask(
                    prompt, session_id="outline", strict=True,
                    cancel_event=cancel)
                if cancel.is_set():
                    self._finish_task_card("生成大纲", "已取消", theme.text_disabled)
                    return
                self.ai_chat.show_prompt_bubble(result)
                self.ai_chat.update_task_card("请回复上方紫色气泡中的问题...")
                busy_seen = False
                for _ in range(300):
                    if cancel.is_set():
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
            "检查所有验收中（inspection）任务，评估提交质量。"
            "对每个任务给出审核建议：同意/驳回/需补充信息，并说明理由。"
            "不要直接移动任务——只提供建议供人工审核。"
        ),
    }

    def _cmd_gen_tasks(self):
        if not self.ai_chat:
            Toast.show(self._page, "AI 面板未就绪", "warning"); return
        if self.ai_chat.is_task_running:
            Toast.show(self._page, "AI 正在处理中，请等待当前任务完成", "warning"); return
        self._open_ai_panel()
        self.ai_chat.show_task_card("生成任务")

        import threading, time

        def _do_gen():
            import traceback
            cancel = self.ai_chat._cancel_event if self.ai_chat else None
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
                if cancel.is_set():
                    self._finish_task_card("生成任务", "已取消", theme.text_disabled)
                    return

                # 显示 Agent 提问为紫色需求气泡
                self.ai_chat.show_prompt_bubble(result)
                self.ai_chat.update_task_card("请回复上方紫色气泡中的问题...")
                known_before = {t.id for t in state.get_all_tasks()}
                busy_seen = False
                for _ in range(300):
                    if cancel.is_set():
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
        print("[CLASSIFY] _cmd_classify called")
        if not self.ai_chat:
            print("[CLASSIFY] no ai_chat!"); return
        if self.ai_chat.is_task_running:
            print("[CLASSIFY] task already running"); return
        backlog = [t for t in state.get_all_tasks() if t.status.value == "backlog"]
        print(f"[CLASSIFY] backlog count={len(backlog)}")
        if not backlog:
            self._open_ai_panel()
            self._show_ai_in_panel("自动分类", "待处理列中没有任务需要分类。")
            return
        tasks_str = "\n".join(
            f"- [{t.id}] {t.title} (ATA {t.ata_chapter or '未指定'}, 飞机 {t.aircraft_reg or '未指定'})"
            for t in backlog
        )
        self._open_ai_panel()
        self.ai_chat.show_task_card("自动分类")
        self.ai_chat.update_task_card(f"正在分析 {len(backlog)} 个任务...")

        import threading, traceback

        def _do():
            print("[CLASSIFY] _do thread started")
            cancel = self.ai_chat._cancel_event
            print(f"[CLASSIFY] cancel_event={cancel}")
            try:
                from app.ui.services.agent_service import AgentService
                prompt = (f"{self._CMD_PROMPTS['classify']}\n\n"
                          f"待处理任务:\n{tasks_str}\n\n使用 classify_task 逐个分类。")
                self.ai_chat.update_task_card("正在执行分类...", border_color=theme.warning)
                pending_before = {t.id for t in state.get_all_tasks() if t.ai_proposed}
                print(f"[CLASSIFY] before ask, pending_before={len(pending_before)}")
                result = AgentService.ask(prompt, session_id="classify", cancel_event=cancel)
                print(f"[CLASSIFY] ask done, result_len={len(result) if result else 0}")
                if cancel.is_set():
                    self._finish_task_card("自动分类", "已取消", theme.text_disabled)
                    return
                self._refresh_board()
                pending_after = {t.id for t in state.get_all_tasks() if t.ai_proposed}
                pending = pending_after - pending_before
                if pending:
                    self._poll_ghost_resolution("自动分类", pending, cancel)
                else:
                    self._finish_task_card("自动分类", "完成（无幽灵卡）", theme.success)
            except Exception as ex:
                self._finish_task_card("自动分类", f"失败: {ex}", theme.error)

        print("[CLASSIFY] starting thread")
        threading.Thread(target=_do, daemon=True).start()
        print("[CLASSIFY] thread started")

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
        self._open_ai_panel()
        self.ai_chat.show_task_card("自动排程")
        self.ai_chat.update_task_card(f"正在分析 {len(triage)} 个任务...")

        import threading
        def _do():
            cancel = self.ai_chat._cancel_event
            try:
                from app.ui.services.agent_service import AgentService
                prompt = (f"{self._CMD_PROMPTS['schedule']}\n\n"
                          f"已分类任务:\n{tasks_str}\n\n"
                          f"使用 search_employees + schedule_task 逐个排程。")
                self.ai_chat.update_task_card("正在执行排程...", border_color=theme.warning)
                pending_before = {t.id for t in state.get_all_tasks() if t.ai_proposed}
                result = AgentService.ask(prompt, session_id="schedule", cancel_event=cancel)
                if cancel.is_set():
                    self._finish_task_card("自动排程", "已取消", theme.text_disabled)
                    return
                self._refresh_board()
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
        if not self.ai_chat:
            Toast.show(self._page, "AI 面板未就绪", "warning"); return
        if self.ai_chat.is_task_running:
            Toast.show(self._page, "AI 正在处理中，请等待当前任务完成", "warning"); return
        insp = [t for t in state.get_all_tasks() if t.status.value == "inspection"]
        if not insp:
            self._open_ai_panel()
            self._show_ai_in_panel("自动验收", "验收列中没有任务。")
            return
        tasks_str = "\n".join(
            f"- [{t.id}] {t.title} (负责人: {t.employee_name or '未指定'})"
            for t in insp
        )
        self._open_ai_panel()
        self.ai_chat.show_task_card("自动验收")
        self.ai_chat.update_task_card(f"正在审核 {len(insp)} 个任务...")

        import threading
        def _do():
            cancel = self.ai_chat._cancel_event
            try:
                from app.ui.services.agent_service import AgentService
                prompt = (f"{self._CMD_PROMPTS['acceptance']}\n\n"
                          f"验收任务:\n{tasks_str}\n\n"
                          f"使用 get_task_detail 查看详情后给出审核建议。")
                self.ai_chat.update_task_card("正在审核提交日志...", border_color=theme.warning)
                result = AgentService.ask(prompt, session_id="acceptance", cancel_event=cancel)
                if cancel.is_set():
                    self._finish_task_card("自动验收", "已取消", theme.text_disabled)
                    return
                self.ai_chat.update_task_card("验收完成", border_color=theme.success)
                self.ai_chat.show_status_bubble("自动验收 完成", theme.success)
                self._show_ai_in_panel("自动验收", result)
            except Exception as ex:
                self.ai_chat.update_task_card(f"失败: {ex}", border_color=theme.error)
            finally:
                import time; time.sleep(1.5)
                self.ai_chat.hide_task_card()

        threading.Thread(target=_do, daemon=True).start()

    def _run_agent_cmd(self, cmd: str, prompt: str):
        """通用 Agent 命令——打开 AI 面板并执行。"""
        self._open_ai_panel()
        if not self.ai_chat:
            return
        # 将命令注入 AI 面板的 send 流程
        try:
            from app.ui.services.agent_service import AgentService
            result = AgentService.ask(prompt, session_id=cmd)
            self._show_ai_in_panel(_cmd_labels.get(cmd, cmd), result)
        except Exception as e:
            Toast.show(self._page, f"执行失败: {e}", "warning")

    # ═══════════════════════════════════════════
    # 6. 生成报表 → 弹窗显示 MD 报表、可保存
    # ═══════════════════════════════════════════

    def _cmd_report(self):
        ff = theme.font_family
        report_f = ft.TextField(
            value="正在生成报表...", read_only=True, multiline=True,
            min_lines=12, max_lines=20,
            border_color=theme.border,
            text_style=ft.TextStyle(color="#c0c0c0", size=s(11), font_family=ff),
            bgcolor=theme.card, border_radius=s(6),
        )
        progress = ft.ProgressRing(width=s(16), height=s(16))

        def _save(e):
            import os
            os.makedirs("data/reports", exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = f"data/reports/report_{ts}.md"
            with open(path, "w", encoding="utf-8") as f:
                f.write(report_f.value or "")
            Toast.show(self._page, f"已保存: {path}", "success"); dlg.close()

        content = ft.Column([
            ft.Row([
                ft.Text("生成维护报表", size=s(14), weight=ft.FontWeight.W_600,
                        color=theme.text_primary, font_family=ff),
                progress,
            ], spacing=s(8)),
            ft.Container(height=s(8)),
            report_f,
            ft.Container(height=s(8)),
            ft.Row([
                ft.Container(expand=True),
                ft.TextButton("关闭", on_click=lambda e: dlg.close()),
                ft.ElevatedButton("保存报表", on_click=_save,
                    style=ft.ButtonStyle(bgcolor=theme.success, color=ft.Colors.WHITE,
                        shape=ft.RoundedRectangleBorder(radius=s(6)))),
            ]),
        ], spacing=0, tight=True)
        from app.ui.components.modal_dialog import ModalDialog
        dlg = ModalDialog(self._page, content, width=640)
        dlg.open()

        # 异步生成报表
        import threading
        def _gen():
            try:
                from app.ui.services.agent_service import AgentService
                r = AgentService.generate_report("daily")
                report_f.value = r
            except Exception as ex:
                report_f.value = f"生成失败: {ex}"
            progress.visible = False
            try: progress.update(); report_f.update()
            except Exception: pass
        threading.Thread(target=_gen, daemon=True).start()

    # ═══════════════════════════════════════════
    # 7. 任务审核 → 弹窗显示合规问题
    # ═══════════════════════════════════════════

    def _cmd_review(self):
        ff = theme.font_family
        review_f = ft.TextField(
            value="正在审核任务合规性...", read_only=True, multiline=True,
            min_lines=10, max_lines=18,
            border_color=theme.border,
            text_style=ft.TextStyle(color="#c0c0c0", size=s(11), font_family=ff),
            bgcolor=theme.card, border_radius=s(6),
        )
        progress = ft.ProgressRing(width=s(16), height=s(16))

        content = ft.Column([
            ft.Row([
                ft.Text("任务合规审核", size=s(14), weight=ft.FontWeight.W_600,
                        color=theme.text_primary, font_family=ff),
                progress,
            ], spacing=s(8)),
            ft.Container(height=s(8)),
            review_f,
            ft.Container(height=s(8)),
            ft.Row([
                ft.Container(expand=True),
                ft.TextButton("关闭", on_click=lambda e: dlg.close()),
            ]),
        ], spacing=0, tight=True)
        from app.ui.components.modal_dialog import ModalDialog
        dlg = ModalDialog(self._page, content, width=640)
        dlg.open()

        import threading
        def _review():
            try:
                from app.ui.services.agent_service import AgentService
                r = AgentService.task_review()
                review_f.value = r
            except Exception as ex:
                review_f.value = f"审核失败: {ex}"
            progress.visible = False
            try: progress.update(); review_f.update()
            except Exception: pass
        threading.Thread(target=_review, daemon=True).start()

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
        if action == "delete":
            task_service.delete_task(tid)
            if self.side_panel: self.side_panel.close()
            Toast.show(self._page, "已删除", "info")
        elif action == "search":
            t = state.get_task(tid)
            if t:
                query = f"{t.title} ATA {t.ata_chapter}"
                self._do_agent_query(query)
        elif action == "ai_explain":
            t = state.get_task(tid)
            if t:
                query = f"解释以下维修任务：{t.title}，飞机{t.aircraft_reg}，ATA章节{t.ata_chapter}"
                self._do_agent_query(query)
        elif action == "submit":
            self._dlg_submit(tid)
        elif action == "edit":
            t = state.get_task(tid)
            if t and self.side_panel:
                if self.ai_chat and self.ai_chat.is_open:
                    self.ai_chat.close()
                self.side_panel.open_task(t)
                self._page.update()

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

        from app.ui.components.modal_dialog import ModalDialog
        content = ft.Column([
            ft.Text(f"提交验收: {t.title[:30]}...", size=theme.font_lg,
                    weight=ft.FontWeight.W_600, color=theme.text_primary, font_family=ff),
            ft.Text("交接班日志将作为 AI 审核的提交材料", size=s(11),
                    color=theme.text_secondary, font_family=ff),
            ft.Container(height=8),
            result_f, hours_f,
            ft.Container(height=8),
            ft.Row([
                ft.Container(expand=True),
                ft.TextButton("取消", on_click=lambda e: dlg.close()),
                ft.ElevatedButton("提交验收", on_click=submit,
                                  style=ft.ButtonStyle(bgcolor=theme.info)),
            ]),
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
            if readonly:
                return ft.Text(str(value or "—"), size=s(13),
                               color=theme.text_disabled, font_family=ff)
            return ft.TextField(
                hint_text=hint, value=str(value or ""),
                border_color=theme.border, focused_border_color=theme.info,
                cursor_color=theme.info,
                text_style=ft.TextStyle(color="#e0e0e0", size=s(13), font_family=ff),
                hint_style=ft.TextStyle(color=theme.text_secondary, size=s(12), font_family=ff),
                bgcolor=theme.card, dense=True,
                content_padding=ft.padding.only(left=s(10), top=s(8), right=s(10), bottom=s(8)),
                border_radius=s(6), **kw)

        def _label(text, required=False):
            if required:
                return ft.Text(spans=[
                    ft.TextSpan(text, ft.TextStyle(color=theme.text_primary, size=s(12), font_family=ff, weight=ft.FontWeight.W_500)),
                    ft.TextSpan(" *", ft.TextStyle(color=theme.error, size=s(12), font_family=ff, weight=ft.FontWeight.W_500))])
            return ft.Text(text, size=s(12), color=theme.text_primary, font_family=ff, weight=ft.FontWeight.W_500)

        def _col(lbl, ctrl):
            return ft.Column([lbl, ctrl], spacing=s(4), tight=True, expand=True)

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
            print(f"[EDIT] title='{task.title}' locked=True (plain TF)")
        else:
            title_gf = GhostTextField(
                hint_text="任务标题", field_name="title",
                get_context=_get_ctx, on_field_filled=_on_filled,
            )
            title_gf.value = task.title
            _fields["title"] = title_gf
            print(f"[EDIT] title='{task.title}' locked=False (GhostTextField)")

        # ── 描述 ──
        if _DESC_LOCKED:
            desc_gf = ft.Text(task.description or "—", size=s(13),
                               color=theme.text_disabled, font_family=ff)
            _fields["description"] = desc_gf
            print(f"[EDIT] desc='{(task.description or '')[:30]}' locked=True (plain TF)")
        else:
            desc_gf = GhostTextField(
                hint_text="任务描述", field_name="description",
                get_context=_get_ctx, on_field_filled=_on_filled,
                multiline=True, min_lines=3,
            )
            desc_gf.value = task.description or ""
            _fields["description"] = desc_gf
            print(f"[EDIT] desc='{(task.description or '')[:30]}' locked=False (GhostTextField)")

        # ── 飞机注册号 ──
        reg_f = _norm_tf("飞机注册号，如 B-5823", str(task.aircraft_reg or ""), readonly=_CORE_LOCKED)
        print(f"[EDIT] reg='{task.aircraft_reg}' locked={_CORE_LOCKED}")
        _fields["aircraft_reg"] = reg_f

        # ── ATA 章节 ──
        if _CORE_LOCKED:
            ata_gf = _norm_tf("ATA 章节，如 32-41-03", str(task.ata_chapter or ""), readonly=True)
            _fields["ata_chapter"] = ata_gf
            print(f"[EDIT] ata='{task.ata_chapter}' locked=True (plain TF)")
        else:
            ata_gf = GhostTextField(
                hint_text="ATA 章节，如 32-41-03", field_name="ata_chapter",
                get_context=_get_ctx, on_field_filled=_on_filled,
            )
            ata_gf.value = task.ata_chapter or ""
            _fields["ata_chapter"] = ata_gf
            print(f"[EDIT] ata='{task.ata_chapter}' locked=False (GhostTextField)")

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
        print(f"[EDIT] emp_id='{task.employee_id}' name='{task.employee_name}' locked={_EMP_LOCKED}")
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
        print(f"[EDIT] planned_start={task.planned_start} planned_end={task.planned_end} hrs={task.estimated_hours} locked={_TIME_LOCKED}")

        # 仅 backlog/triage 有时分校验
        if not _TIME_LOCKED:
            def _clamp_tf(tf, hi):
                val = (tf.value or "").strip()
                if val:
                    if not val.isdigit(): tf.value = ""; tf.update(); return
                    n = int(val)
                    if n > hi: tf.value = str(hi); tf.update()
            for _tf, _hi in [(sh, 23), (sm, 59), (eh, 23), (em, 59)]:
                _tf.on_blur = lambda e, t=_tf, h=_hi: _clamp_tf(t, h)

        def _make_date_picker(initial_date=None):
            state = {"date": initial_date}
            dp = ft.DatePicker(first_date=dt(2024, 1, 1), last_date=dt(2030, 12, 31),
                               on_change=lambda e: _on_pick(e))
            if initial_date:
                display = ft.Text(initial_date.strftime("%Y-%m-%d"), size=s(12), color="#e0e0e0", font_family=ff)
            elif _TIME_LOCKED:
                display = ft.Text("—", size=s(12), color=theme.text_secondary, font_family=ff)
            else:
                display = ft.Text("点击选择日期", size=s(12), color=theme.text_secondary, font_family=ff)
            ctrl = ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.CALENDAR_TODAY_OUTLINED, size=s(14),
                            color=theme.text_secondary),
                    display,
                ], spacing=s(6)),
                bgcolor=theme.card,
                border_radius=s(6),
                border=ft.border.all(1, theme.border),
                padding=ft.padding.only(left=s(10), top=s(8), right=s(10), bottom=s(8)),
                on_click=None if _TIME_LOCKED else (lambda e: self._page.open(dp)),
                ink=not _TIME_LOCKED)
            def _on_pick(e):
                if e.control.value:
                    state["date"] = e.control.value
                    display.value = state["date"].strftime("%Y-%m-%d")
                    display.color = "#e0e0e0"
                    ctrl.update(); _recalc_hours()
            def _set_err(msg):
                display.value = msg; display.color = theme.error
                ctrl.border = ft.border.all(1, theme.error); ctrl.update()
            def _clear_err():
                if state["date"]:
                    display.value = state["date"].strftime("%Y-%m-%d"); display.color = "#e0e0e0"
                else:
                    display.value = "点击选择日期"; display.color = theme.text_secondary
                ctrl.border = ft.border.all(1, theme.border); ctrl.update()
            return ctrl, state, _set_err, _clear_err

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
            start_date_ctrl, start_date_state, start_date_err, start_date_clr = _make_date_picker(
                initial_date=task.planned_start)
            due_date_ctrl, due_date_state, due_date_err, due_date_clr = _make_date_picker(
                initial_date=task.planned_end)

        def _get_dt(date_state, h_f, m_f):
            d = date_state["date"]
            if not d: return None
            h = (h_f.value or "").strip()
            m = (m_f.value or "").strip()
            if h and m:
                try: return dt(d.year, d.month, d.day, int(h), int(m))
                except: pass
            return d

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
        print(f"[EDIT] zone='{task.zone}' locked={_ZONE_LOCKED}")
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

        print(f"[EDIT] opening dialog: st={st} locked={{core:{_CORE_LOCKED} pri:{_PRI_LOCKED} type:{_TYPE_LOCKED} emp:{_EMP_LOCKED} time:{_TIME_LOCKED} zone:{_ZONE_LOCKED} title:{_TITLE_LOCKED} desc:{_DESC_LOCKED} log:{_LOG_LOCKED}}}")

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

        header = ft.Container(
            ft.Row([
                ft.Icon(ft.Icons.FILTER_ALT_OUTLINED, size=s(15), color="#5294e2"),
                ft.Text("筛选任务", size=s(14), weight=ft.FontWeight.W_600,
                        color=theme.text_primary, font_family=ff),
                ft.Container(expand=True),
                ft.IconButton(ft.Icons.CLOSE, icon_size=s(16),
                              icon_color=theme.text_secondary,
                              style=ft.ButtonStyle(
                                  bgcolor=ft.Colors.TRANSPARENT,
                                  overlay_color=ft.Colors.RED_900,
                                  shape=ft.RoundedRectangleBorder(radius=s(4))),
                              on_click=lambda e: dlg.close()),
            ], spacing=s(8)),
            padding=ft.padding.only(left=s(14), top=s(8), right=s(6), bottom=s(8)),
            border=ft.border.only(bottom=ft.BorderSide(1, theme.border)),
        )

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

        btn_style = ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=s(6)),
            padding=ft.padding.only(left=s(18), top=s(7), right=s(18), bottom=s(7)),
            text_style=ft.TextStyle(size=s(12), font_family=ff),
        )
        footer = ft.Container(
            ft.Row([
                ft.Container(expand=True),
                ft.OutlinedButton("清除", on_click=_clear,
                    style=ft.ButtonStyle(
                        shape=btn_style.shape, padding=btn_style.padding,
                        text_style=btn_style.text_style,
                        side=ft.BorderSide(1, theme.border),
                        color=theme.text_secondary)),
                ft.ElevatedButton("应用筛选", on_click=_apply,
                    style=ft.ButtonStyle(
                        shape=btn_style.shape, padding=btn_style.padding,
                        text_style=btn_style.text_style,
                        bgcolor="#5294e2", color=ft.Colors.WHITE, elevation=0)),
            ], spacing=s(8)),
            padding=ft.padding.only(left=s(14), top=s(8), right=s(14), bottom=s(10)),
            border=ft.border.only(top=ft.BorderSide(1, theme.border)),
        )

        content = ft.Column([header, form, footer], spacing=0, tight=True)
        dlg = ModalDialog(self._page, content, width=360)
        dlg.open()


_cmd_labels = {
    "gen_tasks": "生成任务", "classify": "自动分类",
    "schedule": "自动排程", "acceptance": "自动验收",
    "report": "生成报表", "review": "任务审核",
}
