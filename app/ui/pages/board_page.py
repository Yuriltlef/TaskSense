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
        self._drag_start_width: float | None = None
        self._drag_start_x: float | None = None
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
            hint_text="搜索任务...",
            border_color=theme.border,
            focused_border_color="#5294e2",
            cursor_color=theme.text_primary,
            cursor_height=s(14),
            text_style=ft.TextStyle(color=theme.text_primary, size=s(13), font_family=ff),
            hint_style=ft.TextStyle(color=theme.text_disabled,
                                    size=s(12), font_family=ff),
            content_padding=ft.padding.only(left=s(10), top=s(5),
                                            right=s(10), bottom=s(5)),
            dense=True,
            width=220,
            bgcolor="#0d0d0d",
            border_radius=s(16),
            border=ft.border.all(1, theme.border),
            on_change=self._on_search_input,
            on_submit=self._on_search_submit,
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
        for ids in bs.tasks.values():
            for tid in ids:
                t = state.get_task(tid)
                if t: tasks_map[tid] = t
        self.kanban_board.render_board(bs, tasks_map, do_update=False)
        s = board_service.get_fleet_summary()
        if self.fleet_status: self.fleet_status._build(s)

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
            ("inspection", "C 检 — 机身结构详细检查", "B-5823", "53-10-01", "cat_c", "inspection", "王", 48.0, "100"),
            ("parts_hold", "左发点火电嘴更换", "B-9076", "74-11-03", "cat_a", "removal_install", "赵", 3.0, "420"),
            ("completed", "驾驶舱仪表灯光检查", "B-2518", "33-11-01", "cat_d", "inspection", "李", 1.0, "110"),
            ("completed", "APU 进气门清洁", "B-5823", "49-11-01", "cat_d", "servicing", "张", 2.0, "310"),
        ]
        status_order = ["backlog", "triage", "scheduled", "ready",
                        "in_progress", "inspection", "parts_hold", "completed"]
        due_map = {"aog": 4, "cat_a": 24, "cat_b": 72, "cat_c": 168, "cat_d": 720}
        for col_target, title, reg, ata, pri, ttype, who, hrs, zone in demo_tasks:
            task = task_service.create_task(
                title=title, description=f"{title}。ATA {ata}，飞机 {reg}。",
                aircraft_reg=reg, ata_chapter=ata, priority=pri, task_type=ttype,
                assignee=who, estimated_hours=hrs, zone=zone,
                due_date=now + timedelta(hours=due_map.get(pri, 72)),
            )
            if not task: continue
            if col_target != "backlog":
                try:
                    idx = status_order.index(col_target)
                    for i in range(1, idx + 1):
                        mid = status_order[i]
                        if mid == "parts_hold":
                            task_service.update_task(task.id, parts_available=False,
                                                     parts_required=["PN-REQUIRED"])
                        task_service.move_task(task.id, mid, changed_by="demo")
                except Exception: pass

    # ═══════════════════════ 事件 ═══════════════════════

    def _on_state_changed(self): self._refresh_board()

    def _refresh_board(self):
        if not self.kanban_board: return
        bs = board_service.get_board()
        tasks_map = {}
        for ids in bs.tasks.values():
            for tid in ids:
                t = state.get_task(tid)
                if t: tasks_map[tid] = t
        self.kanban_board.render_board(bs, tasks_map)
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
            self.ai_chat.toggle()
            self._page.update()

    def _on_side_panel_close(self):
        if self._page: self._page.update()

    def _on_edit_task(self, task):
        """从侧边栏编辑按钮触发的编辑弹窗。"""
        self._dlg_edit(task)

    def _on_card_context_menu(self, tid, e):
        from app.ui.widgets.context_menu import ContextMenu
        t = state.get_task(tid)
        submit_label = "提交任务" if t and t.status.value != "completed" else "已完成"
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

    def _on_drop(self, tid, col):
        try:
            task_service.move_task(tid, col)
            Toast.show(self._page, f"已移动到 {col}", "success")
        except Exception as e:
            Toast.show(self._page, str(e), "warning")

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

    def _on_search_input(self, e):
        val = (e.control.value or "").strip()
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

    def _do_agent_query(self, question):
        if not question:
            Toast.show(self._page, "请输入问题", "warning"); return
        try:
            from app.ui.services.agent_service import AgentService
            result = AgentService.ask(question)
            self._show_ai_in_panel(f"AI: {question[:50]}", result)
        except Exception as e:
            Toast.show(self._page, f"AI 未就绪: {e}", "warning")

    def _show_ai_in_panel(self, title: str, content: str):
        if self.ai_chat:
            if self.side_panel and self.side_panel.is_open: self.side_panel.close()
            self.ai_chat.open()
            self._page.update()

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
        """提交任务结果弹窗。"""
        t = state.get_task(tid)
        if not t: return
        ff = theme.font_family
        result_f = ft.TextField(
            label="完成结果", hint_text="描述完成情况、发现的问题...",
            multiline=True, min_lines=3, max_lines=6,
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

        def submit(_):
            result = (result_f.value or "").strip()
            if not result:
                Toast.show(self._page, "请填写完成结果", "warning"); return
            try:
                actual_hours = float(hours_f.value or "0")
            except ValueError:
                actual_hours = 0
            try:
                task_service.move_task(tid, "completed", changed_by="user")
                t.actual_hours = actual_hours
                if result:
                    t.description = f"{t.description}\n\n[提交结果] {result}"
                dlg.close()
                Toast.show(self._page, "任务已提交完成", "success")
            except Exception as e:
                Toast.show(self._page, str(e), "warning")

        from app.ui.components.modal_dialog import ModalDialog
        content = ft.Column([
            ft.Text(f"提交任务: {t.title[:30]}...", size=theme.font_lg,
                    weight=ft.FontWeight.W_600, color=theme.text_primary, font_family=ff),
            ft.Container(height=8),
            result_f, hours_f,
            ft.Container(height=8),
            ft.Row([
                ft.Container(expand=True),
                ft.TextButton("取消", on_click=lambda e: dlg.close()),
                ft.ElevatedButton("提交完成", on_click=submit,
                                  style=ft.ButtonStyle(bgcolor=theme.success)),
            ]),
        ], spacing=0, tight=True)
        dlg = ModalDialog(self._page, content, width=420)
        dlg.open()

    def _dlg_edit(self, task):
        """编辑任务弹窗 — 预填当前值。"""
        ff = theme.font_family
        title_f = ft.TextField(
            label="任务标题", value=task.title,
            border_color=theme.border, focused_border_color=theme.info,
            text_style=ft.TextStyle(color=theme.text_primary, size=theme.font_md, font_family=ff),
            bgcolor=theme.card,
        )
        reg_f = ft.TextField(
            label="飞机注册号", value=task.aircraft_reg, width=200,
            border_color=theme.border, focused_border_color=theme.info,
            text_style=ft.TextStyle(color=theme.text_primary, size=theme.font_md, font_family=ff),
            bgcolor=theme.card,
        )
        ata_f = ft.TextField(
            label="ATA 章节", value=task.ata_chapter, width=200,
            border_color=theme.border, focused_border_color=theme.info,
            text_style=ft.TextStyle(color=theme.text_primary, size=theme.font_md, font_family=ff),
            bgcolor=theme.card,
        )
        assignee_f = ft.TextField(
            label="负责人", value=task.assignee or "", width=200,
            border_color=theme.border, focused_border_color=theme.info,
            text_style=ft.TextStyle(color=theme.text_primary, size=theme.font_md, font_family=ff),
            bgcolor=theme.card,
        )
        zone_f = ft.TextField(
            label="区域 (Zone)", value=task.zone or "", width=200,
            border_color=theme.border, focused_border_color=theme.info,
            text_style=ft.TextStyle(color=theme.text_primary, size=theme.font_md, font_family=ff),
            bgcolor=theme.card,
        )

        def save(_):
            t = (title_f.value or "").strip()
            if not t: Toast.show(self._page, "请输入标题", "warning"); return
            task.title = t
            task.aircraft_reg = (reg_f.value or "").strip()
            task.ata_chapter = (ata_f.value or "").strip()
            task.assignee = (assignee_f.value or "").strip() or None
            task.zone = (zone_f.value or "").strip() or None
            dlg.close()
            self._refresh_board()
            Toast.show(self._page, "任务已更新", "success")

        from app.ui.components.modal_dialog import ModalDialog
        content = ft.Column([
            ft.Text("编辑任务", size=theme.font_lg, weight=ft.FontWeight.W_600,
                    color=theme.text_primary, font_family=ff),
            ft.Container(height=8),
            title_f,
            ft.Row([reg_f, ata_f], spacing=12),
            ft.Row([assignee_f, zone_f], spacing=12),
            ft.Container(height=8),
            ft.Row([
                ft.Container(expand=True),
                ft.TextButton("取消", on_click=lambda e: dlg.close()),
                ft.ElevatedButton("保存", on_click=save, style=ft.ButtonStyle(bgcolor=theme.info)),
            ]),
        ], spacing=0, tight=True)
        dlg = ModalDialog(self._page, content, width=460)
        dlg.open()

    def _dlg_filter(self):
        ata_dd = ft.Dropdown(
            label="ATA 章节",
            options=[ft.dropdown.Option(k, v) for k, v in [
                ("21", "21 - 空调"), ("24", "24 - 电源"), ("27", "27 - 飞行控制"),
                ("28", "28 - 燃油"), ("32", "32 - 起落架"), ("49", "49 - APU"),
                ("72", "72 - 发动机"), ("79", "79 - 滑油")]],
            border_color=theme.border, bgcolor=theme.card)
        pri_dd = ft.Dropdown(
            label="优先级",
            options=[ft.dropdown.Option(k, v) for k, v in [
                ("aog", "AOG"), ("cat_a", "Cat A"), ("cat_b", "Cat B"), ("cat_c", "Cat C")]],
            border_color=theme.border, bgcolor=theme.card)

        def apply(_):
            f = FilterState()
            if ata_dd.value: f.ata_chapters = [ata_dd.value]
            if pri_dd.value: f.priorities = [pri_dd.value]
            board_service.set_filters(f)
            dlg.close()
            Toast.show(self._page, "筛选已应用", "info")

        def clear(_):
            board_service.set_filters(FilterState())
            dlg.close()
            Toast.show(self._page, "筛选已清除", "info")

        from app.ui.components.modal_dialog import ModalDialog
        content = ft.Column([
            ft.Text("筛选", size=theme.font_lg, weight=ft.FontWeight.W_600,
                    color=theme.text_primary, font_family=theme.font_family),
            ft.Container(height=8),
            ata_dd, pri_dd,
            ft.Container(height=8),
            ft.Row([
                ft.TextButton("清除", on_click=clear),
                ft.Container(expand=True),
                ft.ElevatedButton("应用", on_click=apply, style=ft.ButtonStyle(bgcolor=theme.info)),
            ]),
        ], spacing=0, tight=True)
        dlg = ModalDialog(self._page, content, width=340)
        dlg.open()
