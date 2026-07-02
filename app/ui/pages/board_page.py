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

        def _date_picker():
            from datetime import datetime as dt
            state = {"date": None, "time": ""}
            dp = ft.DatePicker(first_date=dt(2024,1,1), last_date=dt(2030,12,31),
                on_change=lambda e: _on_pick(e))
            display = ft.Text("", size=s(12), color=theme.text_secondary, font_family=ff)
            hour_opts = [(f"{h:02d}:00", f"{h:02d}:00") for h in range(0, 24, 2)]
            time_dd = ft.Dropdown(value="", options=[ft.dropdown.Option(k,v) for k,v in hour_opts],
                dense=True, width=s(78), max_menu_height=s(150),
                border_color=theme.border, focused_border_color=theme.info, bgcolor=theme.card,
                text_style=ft.TextStyle(color="#e0e0e0", size=s(11), font_family=ff),
                border_radius=s(6),
                content_padding=ft.padding.only(left=s(6), top=s(3), right=s(4), bottom=s(3)),
                on_change=lambda e: _on_time(e))
            container = ft.Container(
                content=ft.Row([ft.Icon(ft.Icons.CALENDAR_TODAY_OUTLINED, size=s(14), color=theme.text_secondary),
                    display, ft.Container(expand=True),
                    ft.Icon(ft.Icons.SCHEDULE, size=s(14), color=theme.text_secondary), time_dd], spacing=s(6)),
                bgcolor=theme.card, border_radius=s(6), border=ft.border.all(1, theme.border),
                padding=ft.padding.only(left=s(10), top=s(6), right=s(10), bottom=s(6)),
                on_click=lambda e: self._page.open(dp), ink=True)
            def _on_pick(e):
                if e.control.value: state["date"]=e.control.value; display.value=state["date"].strftime("%Y-%m-%d"); display.color="#e0e0e0"; container.update(); _recalc()
            def _on_time(e):
                state["time"]=time_dd.value or ""; time_dd.border_color=theme.border; _recalc()
            def _set_err(msg): display.value=msg; display.color=theme.error; container.border=ft.border.all(1,theme.error); container.update()
            def _clear_err():
                if state["date"]: display.value=state["date"].strftime("%Y-%m-%d"); display.color="#e0e0e0"
                else: display.value=""; display.color=theme.text_secondary
                container.border=ft.border.all(1,theme.border); container.update()
            def _get_dt():
                d=state["date"]; t=state["time"]
                if not d: return None
                if t:
                    try: h,m=t.split(":"); return dt(d.year,d.month,d.day,int(h),int(m))
                    except: pass
                return d
            return container, state, _set_err, _clear_err, _get_dt

        start_ctrl, start_state, start_err, start_clr, start_get = _date_picker()
        due_ctrl, due_state, due_err, due_clr, due_get = _date_picker()

        def _recalc():
            sd=start_get(); ed=due_get()
            if sd and ed:
                diff=(ed-sd).total_seconds()/3600
                if diff>0: hours_f.value=f"{diff:.1f}"; hours_f.update()

        def _confirm(_):
            from app.ui.widgets.toast import Toast
            start_dt=start_get(); due_dt=due_get()
            hs=(hours_f.value or "").strip()
            aid=(assignee_id_f.value or "").strip()
            aname=(assignee_name_f.value or "").strip()
            start_clr(); due_clr()
            for c,h in [(hours_f,"计划工时 (h)，如 4.5"),(assignee_id_f,"员工 ID，如 ZH001"),(assignee_name_f,"姓名，如 张工")]:
                c.border_color=theme.border; c.hint_text=h
            if not start_dt: start_err("请选择开始日期"); return
            if not due_dt: due_err("请选择完成日期"); return
            if not hs: hours_f.border_color=theme.error; hours_f.hint_text="请输入计划工时"; hours_f.update(); return
            if not aid: assignee_id_f.border_color=theme.error; assignee_id_f.hint_text="请输入员工 ID"; assignee_id_f.update(); return
            if not aname: assignee_name_f.border_color=theme.error; assignee_name_f.hint_text="请输入姓名"; assignee_name_f.update(); return
            try:
                task_service.move_task(tid,col,index=index)
                updates={"assignee":f"{aid} {aname}"}
                try: updates["estimated_hours"]=float(hs)
                except: pass
                updates["due_date"]=due_dt
                task_service.update_task(tid,**updates)
                Toast.show(self._page,"已排程","success")
            except Exception as ex: Toast.show(self._page,str(ex),"warning")
            dlg.close()

        from app.ui.components.modal_dialog import ModalDialog
        header=ft.Container(
            ft.Row([ft.Icon(ft.Icons.CALENDAR_MONTH_OUTLINED,size=s(15),color="#5294e2"),
                ft.Text("排程信息",size=s(14),weight=ft.FontWeight.W_600,color=theme.text_primary,font_family=ff),
                ft.Container(expand=True),
                ft.IconButton(ft.Icons.CLOSE,icon_size=s(16),icon_color=theme.text_secondary,on_click=lambda e: dlg.close())],spacing=s(8)),
            padding=ft.padding.only(left=s(14),top=s(8),right=s(6),bottom=s(8)),
            border=ft.border.only(bottom=ft.BorderSide(1,theme.border)))
        sep=ft.Divider(height=s(12),color=ft.Colors.TRANSPARENT)
        form=ft.Container(
            ft.Column([_label("计划开始日期",required=True),start_ctrl,sep,
                _label("计划完成日期",required=True),due_ctrl,sep,
                ft.Row([_col(_label("计划工时",required=True),hours_f),ft.Container(expand=True)],spacing=s(12)),sep,
                ft.Row([_col(_label("员工 ID",required=True),assignee_id_f),_col(_label("姓名",required=True),assignee_name_f)],spacing=s(12)),
            ],spacing=s(4),tight=True),
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
        dlg=ModalDialog(self._page,content,width=520,bgcolor="#1c1c1c")
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
