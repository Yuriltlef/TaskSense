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
        self._search_clear_btn: ft.IconButton | None = None
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
        """将 AI 建议的任务渲染为幽灵卡片（注入列 ListView）。"""
        from app.ui.widgets.ai_ghost_card import AIGhostCard, AIProposal, GhostCardManager
        if not hasattr(self, '_ghost_mgr'):
            self._ghost_mgr = GhostCardManager()

        for col in self.kanban_board._columns.values():
            if not hasattr(col, 'card_list') or not col.card_list:
                continue
            # 清除已有的幽灵卡片
            to_remove = [c for c in col.card_list.controls
                         if isinstance(c, AIGhostCard)]
            for c in to_remove:
                col.card_list.controls.remove(c)

        for tid, t in ai_tasks.items():
            col_id = t.status.value
            if col_id not in self.kanban_board._columns:
                continue
            col = self.kanban_board._columns[col_id]
            if not hasattr(col, 'card_list') or not col.card_list:
                continue
            proposal = AIProposal(
                id=f"ai_{tid}",
                proposal_type="new_task",
                task_data={
                    "id": tid, "title": t.title, "description": t.description,
                    "ata_chapter": t.ata_chapter, "aircraft_reg": t.aircraft_reg,
                    "priority": t.priority.value, "task_type": t.task_type.value,
                    "zone": t.zone, "estimated_hours": t.estimated_hours,
                },
                target_column=col_id,
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
        """接受 AI 建议任务——去除幽灵标记变为正式任务。"""
        state.update_task(tid, ai_proposed=False)
        from app.ui.widgets.toast import Toast
        Toast.show(self._page, "AI 建议任务已接受", "success")
        self._refresh_board()

    def _reject_ai_task(self, tid):
        """拒绝 AI 建议任务——删除。"""
        state.delete_task(tid)
        from app.ui.widgets.toast import Toast
        Toast.show(self._page, "AI 建议任务已拒绝", "info")
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
            ("inspection", "C 检 — 机身结构详细检查", "B-5823", "53-10-01", "cat_c", "inspection", "王", 48.0, "100"),
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
        due_map = {"aog": 4, "cat_a": 24, "cat_b": 72, "cat_c": 168, "cat_d": 720}
        for col_target, title, reg, ata, pri, ttype, who, hrs, zone in demo_tasks:
            task = task_service.create_task(
                title=title, description=f"{title}。ATA {ata}，飞机 {reg}。",
                aircraft_reg=reg, ata_chapter=ata, priority=pri, task_type=ttype,
                assignee=who, estimated_hours=hrs, zone=zone,
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
                except Exception: pass

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
    # 1. 生成大纲 → 弹窗显示、可保存
    # ═══════════════════════════════════════════

    def _cmd_outline(self):
        """打开大纲生成弹窗。"""
        ff = theme.font_family
        desc_f = ft.TextField(
            hint_text="描述维护需求，如：B-5823 左发起落架收放测试...",
            border_color=theme.border, focused_border_color=theme.info,
            text_style=ft.TextStyle(color="#e0e0e0", size=s(13), font_family=ff),
            bgcolor=theme.card, multiline=True, min_lines=3, max_lines=6,
            border_radius=s(6), dense=True,
        )
        result_f = ft.TextField(
            value="", read_only=True, multiline=True, min_lines=8, max_lines=16,
            border_color=theme.border,
            text_style=ft.TextStyle(color="#c0c0c0", size=s(11), font_family=ff),
            bgcolor=theme.card, border_radius=s(6),
        )
        progress = ft.ProgressRing(width=s(16), height=s(16), visible=False)

        def _generate(e):
            q = (desc_f.value or "").strip()
            if not q:
                Toast.show(self._page, "请输入维护需求描述", "warning"); return
            progress.visible = True; result_f.value = "正在生成大纲..."; progress.update(); result_f.update()
            try:
                from app.ui.services.agent_service import AgentService
                outline = AgentService.generate_outline(q)
                result_f.value = outline
            except Exception as ex:
                result_f.value = f"生成失败: {ex}"
            progress.visible = False; progress.update(); result_f.update()

        def _save_file(e):
            import os
            os.makedirs("data/outlines", exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = f"data/outlines/outline_{ts}.md"
            with open(path, "w", encoding="utf-8") as f:
                f.write(result_f.value or "")
            Toast.show(self._page, f"已保存: {path}", "success"); dlg.close()

        content = ft.Column([
            ft.Text("AI 生成任务大纲", size=s(14), weight=ft.FontWeight.W_600,
                    color=theme.text_primary, font_family=ff),
            ft.Text("描述维护需求，AI 将搜索知识库并生成结构化大纲", size=s(11),
                    color=theme.text_secondary, font_family=ff),
            ft.Container(height=s(8)),
            desc_f,
            ft.Row([ft.ElevatedButton("生成大纲", on_click=_generate,
                    style=ft.ButtonStyle(bgcolor=theme.info, color=ft.Colors.WHITE,
                        shape=ft.RoundedRectangleBorder(radius=s(6)))),
                    progress], spacing=s(8)),
            ft.Container(height=s(8)),
            result_f,
            ft.Container(height=s(8)),
            ft.Row([
                ft.Container(expand=True),
                ft.TextButton("关闭", on_click=lambda e: dlg.close()),
                ft.ElevatedButton("保存到文件", on_click=_save_file,
                    style=ft.ButtonStyle(bgcolor=theme.success, color=ft.Colors.WHITE,
                        shape=ft.RoundedRectangleBorder(radius=s(6)))),
            ]),
        ], spacing=0, tight=True)
        from app.ui.components.modal_dialog import ModalDialog
        dlg = ModalDialog(self._page, content, width=620)
        dlg.open()

    # ═══════════════════════════════════════════
    # 2. 生成任务 → Agent 调用 create_task 工具 → 幽灵卡
    # 3. 自动分类 → Agent 调用 classify_task 工具 → 幽灵卡
    # 4. 自动排程 → Agent 调用 schedule_task 工具 → 幽灵卡
    # 5. 自动验收 → Agent 审核建议 → 对话面板
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
        self._run_agent_cmd("gen_tasks", self._CMD_PROMPTS["gen_tasks"])

    def _cmd_classify(self):
        self._run_agent_cmd("classify", self._CMD_PROMPTS["classify"])

    def _cmd_schedule(self):
        self._run_agent_cmd("schedule", self._CMD_PROMPTS["schedule"])

    def _cmd_acceptance(self):
        self._run_agent_cmd("acceptance", self._CMD_PROMPTS["acceptance"])

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
        """在 AI 对话面板中显示结果。"""
        if not self.ai_chat or not self.ai_chat.is_open:
            self._open_ai_panel()
        try:
            if hasattr(self.ai_chat, '_msg_pairs'):
                from datetime import datetime
                self.ai_chat._msg_pairs.append((
                    f"[{title}]", content, datetime.now()))
                self.ai_chat._rebuild_bubbles()
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
        """编辑任务弹窗 — 预填当前值，状态约束。"""
        ff = theme.font_family
        st = task.status.value

        # 状态约束规则
        _LOCKED_AFTER_SCHEDULED = ("aircraft_reg", "ata_chapter", "priority")
        _READONLY_STYLES = {"scheduled", "ready", "in_progress",
                            "inspection", "parts_hold", "completed", "archived"}
        _PERSONNEL_READONLY = {"ready", "in_progress", "inspection", "parts_hold", "completed"}
        _TIME_READONLY = {"ready", "in_progress", "inspection", "parts_hold", "completed"}

        def _mk(label, value="", width=None, readonly=False):
            return ft.TextField(
                label=label, value=value or "", width=width,
                border_color=theme.border, focused_border_color=theme.info,
                text_style=ft.TextStyle(color=theme.text_primary, size=s(13), font_family=ff),
                bgcolor=theme.card, dense=True, read_only=readonly,
                border_radius=s(6),
            )

        # 基本信息
        title_f = _mk("任务标题", task.title)
        desc_f = ft.TextField(
            label="任务描述", value=task.description or "",
            border_color=theme.border, focused_border_color=theme.info,
            text_style=ft.TextStyle(color=theme.text_primary, size=s(13), font_family=ff),
            bgcolor=theme.card, multiline=True, min_lines=2, max_lines=4,
            border_radius=s(6), dense=True,
        )

        reg_ro = st in _READONLY_STYLES
        reg_f = _mk("飞机注册号", task.aircraft_reg, readonly=reg_ro)
        ata_ro = st in _READONLY_STYLES
        ata_f = _mk("ATA 章节", task.ata_chapter, readonly=ata_ro)

        # 人员
        emp_ro = st in _PERSONNEL_READONLY
        emp_id_f = _mk("员工 ID", task.employee_id, width=150, readonly=emp_ro)
        emp_name_f = _mk("员工姓名", task.employee_name, width=150, readonly=emp_ro)

        # 时间
        time_ro = st in _TIME_READONLY
        ps_str = task.planned_start.strftime("%Y-%m-%d %H:%M") if task.planned_start else ""
        pe_str = task.planned_end.strftime("%Y-%m-%d %H:%M") if task.planned_end else ""
        ps_f = _mk("计划开始 (YYYY-MM-DD HH:MM)", ps_str, readonly=time_ro)
        pe_f = _mk("计划完成 (YYYY-MM-DD HH:MM)", pe_str, readonly=time_ro)
        hrs_f = _mk("计划工时 (h)", str(task.estimated_hours) if task.estimated_hours else "", width=120, readonly=time_ro)

        # 交接班日志
        log_f = ft.TextField(
            label="交接班日志", value=task.shift_handover_log or "",
            border_color=theme.border, focused_border_color=theme.info,
            text_style=ft.TextStyle(color=theme.text_primary, size=s(13), font_family=ff),
            bgcolor=theme.card, multiline=True, min_lines=2, max_lines=4,
            border_radius=s(6), dense=True,
        )

        def save(_):
            from app.ui.widgets.toast import Toast
            ttl = (title_f.value or "").strip()
            if not ttl:
                Toast.show(self._page, "请输入标题", "warning"); return

            changes = {"title": ttl, "description": (desc_f.value or "").strip()}
            if not reg_ro:
                changes["aircraft_reg"] = (reg_f.value or "").strip().upper()
            if not ata_ro:
                changes["ata_chapter"] = (ata_f.value or "").strip()
            if not emp_ro:
                changes["employee_id"] = (emp_id_f.value or "").strip()
                changes["employee_name"] = (emp_name_f.value or "").strip()
                if changes["employee_name"] and not changes.get("assignee"):
                    changes["assignee"] = changes["employee_name"]
            if not time_ro:
                try:
                    psv = (ps_f.value or "").strip()
                    if psv:
                        changes["planned_start"] = datetime.strptime(psv, "%Y-%m-%d %H:%M")
                    else:
                        changes["planned_start"] = None
                except ValueError:
                    changes["planned_start"] = task.planned_start
                try:
                    pev = (pe_f.value or "").strip()
                    if pev:
                        changes["planned_end"] = datetime.strptime(pev, "%Y-%m-%d %H:%M")
                    else:
                        changes["planned_end"] = None
                except ValueError:
                    changes["planned_end"] = task.planned_end
                try:
                    hv = (hrs_f.value or "").strip()
                    changes["estimated_hours"] = float(hv) if hv else 0.0
                except ValueError:
                    pass
            changes["shift_handover_log"] = (log_f.value or "").strip()

            task_service.update_task(task.id, **changes)
            dlg.close()
            self._refresh_board()
            Toast.show(self._page, "任务已更新", "success")

        header_items = [
            ft.Text("编辑任务", size=s(14), weight=ft.FontWeight.W_600,
                    color=theme.text_primary, font_family=ff),
            ft.Text(f"状态: {task.status.value} | 工卡号: {task.work_order_id or task.id}",
                    size=s(11), color=theme.text_secondary, font_family=ff),
        ]

        body_items = [
            ft.Container(height=s(6)),
            title_f, desc_f,
            ft.Row([reg_f, ata_f], spacing=s(10)),
            ft.Row([emp_id_f, emp_name_f], spacing=s(10)),
            ft.Row([ps_f, pe_f], spacing=s(10)),
            hrs_f,
            log_f,
        ]

        # parts_hold 额外显示取消阻塞按钮
        if st == "parts_hold" and task.is_blocked:
            def _unblock_btn(e):
                try:
                    task_service.unblock_task(task.id, user="user")
                    dlg.close()
                    self._refresh_board()
                    from app.ui.widgets.toast import Toast
                    Toast.show(self._page, "已取消阻塞", "success")
                except Exception as ex:
                    from app.ui.widgets.toast import Toast
                    Toast.show(self._page, f"取消失败: {ex}", "error")
            body_items.append(
                ft.OutlinedButton("取消阻塞", icon=ft.Icons.LOCK_OPEN_OUTLINED,
                    on_click=_unblock_btn,
                    style=ft.ButtonStyle(
                        color=theme.error, side=ft.BorderSide(1, theme.error),
                        shape=ft.RoundedRectangleBorder(radius=s(6)))))

        footer_items = ft.Row([
            ft.Container(expand=True),
            ft.TextButton("取消", on_click=lambda e: dlg.close()),
            ft.ElevatedButton("保存", on_click=save,
                style=ft.ButtonStyle(bgcolor=theme.info)),
        ])

        from app.ui.components.modal_dialog import ModalDialog
        from datetime import datetime
        content = ft.Column([
            ft.Column(header_items, spacing=s(2), tight=True),
            ft.ListView([ft.Column(body_items, spacing=s(4), tight=True)],
                        spacing=0, expand=True, padding=0),
            footer_items,
        ], spacing=0, tight=True)
        dlg = ModalDialog(self._page, content, width=520)
        dlg.open()

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
