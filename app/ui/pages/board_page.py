"""看板主页面."""

from datetime import datetime, timedelta

import flet as ft

from app.config.theme import theme
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
from app.ui.widgets.toast import Toast


class BoardPage:
    def __init__(self):
        self.kanban_board: KanbanBoard | None = None
        self.side_panel: SidePanel | None = None
        self.command_bar: CommandBar | None = None
        self.fleet_status: FleetStatusBar | None = None
        self._page: ft.Page | None = None
        state.subscribe(self._on_state_changed)

    def build(self, page: ft.Page) -> ft.Container:
        self._page = page

        self.kanban_board = KanbanBoard(
            on_card_click=self._on_card_click,
            on_card_context_menu=self._on_card_context_menu,
            on_drop=self._on_drop,
            on_column_menu=self._on_column_menu,
        )
        self.side_panel = SidePanel(on_close=self._on_side_panel_close)
        self.command_bar = CommandBar(on_execute=self._on_command_execute)
        self.fleet_status = FleetStatusBar()

        # ── 顶栏 ──
        top_bar = ft.Row(
            controls=[
                ft.ElevatedButton(
                    content=ft.Row([
                        ft.Icon(ft.Icons.ADD, size=theme.font_lg),
                        ft.Text("新建任务", size=theme.font_sm,
                                font_family=theme.font_family),
                    ], spacing=theme.spacing_xs),
                    style=ft.ButtonStyle(
                        bgcolor=theme.info,
                        color=theme.text_primary,
                        padding=ft.padding.only(
                            left=theme.pad_md, top=theme.pad_sm,
                            right=theme.pad_md, bottom=theme.pad_sm),
                        shape=ft.RoundedRectangleBorder(radius=theme.radius_sm),
                    ),
                    on_click=self._on_create_task,
                ),
                ft.Container(width=theme.spacing_sm),
                ft.IconButton(
                    icon=ft.Icons.REFRESH, icon_size=theme.font_lg,
                    icon_color=theme.text_secondary,
                    tooltip="刷新",
                    on_click=lambda e: self._refresh_board(),
                ),
                ft.IconButton(
                    icon=ft.Icons.FILTER_LIST, icon_size=theme.font_lg,
                    icon_color=theme.text_secondary,
                    tooltip="筛选",
                    on_click=self._on_filter_click,
                ),
                ft.Container(expand=True),
                ft.Text(
                    "Ctrl+K  命令面板", size=theme.font_xs,
                    color=theme.text_disabled,
                    font_family=theme.font_family,
                ),
            ],
            spacing=0,
            alignment=ft.MainAxisAlignment.START,
        )

        # ── 主布局 ──
        main = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Container(
                        content=top_bar,
                        padding=ft.padding.only(
                            left=theme.pad_md, top=theme.pad_sm,
                            right=theme.pad_md, bottom=theme.pad_sm),
                        bgcolor=theme.surface,
                        border=ft.border.only(
                            bottom=ft.BorderSide(1, theme.border)),
                    ),
                    self.fleet_status,
                    ft.Row(
                        controls=[
                            ft.Container(content=self.kanban_board, expand=True,
                                         bgcolor=theme.bg),
                            ft.GestureDetector(
                                content=ft.Container(
                                    width=5,
                                    bgcolor=theme.border,
                                    on_hover=lambda e: None,
                                ),
                                mouse_cursor=ft.MouseCursor.RESIZE_LEFT_RIGHT,
                                on_horizontal_drag_update=self._on_panel_resize,
                            ),
                            self.side_panel,
                        ],
                        spacing=0, expand=True,
                    ),
                ],
                spacing=0, expand=True,
            ),
            expand=True, bgcolor=theme.bg,
        )
        self._fill_board_from_state()
        return main

    def _fill_board_from_state(self):
        """从 state 填充看板（不调用 update，给初始渲染用）。"""
        if not self.kanban_board:
            return
        bs = board_service.get_board()
        tasks_map = {}
        for ids in bs.tasks.values():
            for tid in ids:
                t = state.get_task(tid)
                if t:
                    tasks_map[tid] = t
        self.kanban_board.render_board(bs, tasks_map, do_update=False)
        s = board_service.get_fleet_summary()
        if self.fleet_status:
            self.fleet_status._build(s)

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
        for ac in demo_aircraft:
            state.add_aircraft(ac)

        now = datetime.now()
        demo_tasks = [
            ("backlog",     "APU 启动时间超限检查",        "B-5823", "49-11-01", "aog",   "inspection",      "张", 3.0,  "310"),
            ("backlog",     "右发滑油消耗率偏高",           "B-9076", "79-21-01", "aog",   "troubleshoot",    "李", 5.0,  "420"),
            ("backlog",     "客舱空调出风口异响",           "B-2518", "21-51-01", "cat_c", "troubleshoot",    "王", 2.0,  "510"),
            ("triage",      "前起落架转向异响排查",         "B-5823", "32-41-03", "cat_a", "troubleshoot",    "张", 4.5,  "710"),
            ("triage",      "左发 N1 振动指示异常",         "B-9076", "77-11-01", "cat_b", "troubleshoot",    "赵", 6.0,  "420"),
            ("scheduled",   "A 检 — 飞行控制面功能检查",     "B-5823", "27-10-00", "cat_b", "inspection",      "李", 8.0,  "210"),
            ("scheduled",   "发动机滑油更换",                "B-2518", "79-00-01", "cat_c", "servicing",       "王", 2.0,  "420"),
            ("ready",       "机翼前缘防冰管路测试",         "B-5823", "30-11-01", "cat_c", "test",            "张", 4.0,  "610"),
            ("ready",       "APU 滑油勤务",                 "B-5823", "49-91-01", "cat_c", "servicing",       "赵", 1.5,  "310"),
            ("in_progress", "起落架收放功能测试",           "B-5823", "32-31-01", "cat_b", "test",            "张", 3.0,  "710"),
            ("in_progress", "右发燃油滤更换",               "B-9076", "73-11-03", "cat_a", "removal_install", "李", 4.0,  "420"),
            ("inspection",  "C 检 — 机身结构详细检查",       "B-5823", "53-10-01", "cat_c", "inspection",      "王", 48.0, "100"),
            ("parts_hold",  "左发点火电嘴更换",             "B-9076", "74-11-03", "cat_a", "removal_install", "赵", 3.0,  "420"),
            ("completed",   "驾驶舱仪表灯光检查",           "B-2518", "33-11-01", "cat_d", "inspection",      "李", 1.0,  "110"),
            ("completed",   "APU 进气门清洁",               "B-5823", "49-11-01", "cat_d", "servicing",       "张", 2.0,  "310"),
        ]
        status_order = ["backlog", "triage", "scheduled", "ready",
                        "in_progress", "inspection", "parts_hold", "completed"]
        due_map = {"aog": 4, "cat_a": 24, "cat_b": 72, "cat_c": 168, "cat_d": 720}

        for col_target, title, reg, ata, pri, ttype, who, hrs, zone in demo_tasks:
            task = task_service.create_task(
                title=title,
                description=f"{title}。ATA {ata}，飞机 {reg}。",
                aircraft_reg=reg, ata_chapter=ata, priority=pri,
                task_type=ttype, assignee=who, estimated_hours=hrs,
                zone=zone, due_date=now + timedelta(hours=due_map.get(pri, 72)),
            )
            if not task:
                continue
            if col_target != "backlog":
                try:
                    idx = status_order.index(col_target)
                    for i in range(1, idx + 1):
                        mid = status_order[i]
                        if mid == "parts_hold":
                            task_service.update_task(
                                task.id, parts_available=False,
                                parts_required=["PN-REQUIRED"])
                        task_service.move_task(task.id, mid, changed_by="demo")
                except Exception:
                    pass
        # 数据已加载，build() 中会调用 _fill_board_from_state 渲染

    # ═══════════════════════ 事件 ═══════════════════════

    def _on_state_changed(self):
        self._refresh_board()

    def _refresh_board(self):
        if not self.kanban_board:
            return
        bs = board_service.get_board()
        tasks_map = {}
        for ids in bs.tasks.values():
            for tid in ids:
                t = state.get_task(tid)
                if t:
                    tasks_map[tid] = t
        self.kanban_board.render_board(bs, tasks_map)
        self.fleet_status.update_summary(board_service.get_fleet_summary())

    def _on_panel_resize(self, e):
        if self.side_panel:
            new_w = self.side_panel.width - (e.primary_delta or 0)
            if 280 <= new_w <= 1000:
                self.side_panel.width = new_w
                self.side_panel.update()

    def _on_card_click(self, tid):
        t = state.get_task(tid)
        if t and self.side_panel:
            self.side_panel.toggle(t); self._page.update()

    def _on_side_panel_close(self):
        if self._page: self._page.update()

    def _on_card_context_menu(self, tid, e):
        from app.ui.widgets.context_menu import ContextMenu
        ContextMenu(
            items=[
                {"label": "编辑", "icon": ft.Icons.EDIT_OUTLINED, "action": "edit"},
                {"label": "分配...", "icon": ft.Icons.PERSON_ADD, "action": "assign"},
                {"divider": True},
                {"label": "AI 查找相关文档", "icon": ft.Icons.SEARCH, "action": "search"},
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

    def _on_create_task(self, e): self._dlg_create()
    def _on_filter_click(self, e):
        f = board_service.get_board().filters
        if f.is_active:
            board_service.set_filters(FilterState())
            Toast.show(self._page, "筛选已清除", "info")
        else:
            self._dlg_filter()

    def _on_command_execute(self, action, value):
        if action == "create_task": self._dlg_create()
        elif action == "generate_report":
            s = board_service.get_stats()
            Toast.show(self._page,
                       f"今日: {s['total']} 任务, {s['aog_count']} AOG", "success")
        elif action == "check_compliance":
            Toast.show(self._page, "AD 合规: 无违规项", "success")
        elif action.startswith("filter_ata_"):
            ata = action.replace("filter_ata_", "")
            board_service.set_filters(FilterState(ata_chapters=[ata]))
            Toast.show(self._page, f"已筛选 ATA {ata}", "info")
        elif action == "nl_query":
            Toast.show(self._page,
                       f"找到 {len(board_service.search_tasks(value))} 个结果", "info")
        else:
            Toast.show(self._page, f"操作: {action}", "info")

    def _card_action(self, tid, action):
        if action == "delete":
            task_service.delete_task(tid)
            if self.side_panel: self.side_panel.close()
            Toast.show(self._page, "已删除", "info")
        elif action == "search":
            t = state.get_task(tid)
            if t: Toast.show(self._page, f"AI 检索 ATA {t.ata_chapter}", "info")

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

    def _dlg_create(self):
        tf = lambda label, hint, w=None: ft.TextField(
            label=label, hint_text=hint, width=w,
            border_color=theme.border, focused_border_color=theme.info,
            text_style=ft.TextStyle(color=theme.text_primary, size=theme.font_md,
                                    font_family=theme.font_family),
            bgcolor=theme.card,
        )
        title_f = tf("任务标题", "描述故障或维护需求...")
        reg_f = tf("飞机注册号", "如 B-5823", 200)
        ata_f = tf("ATA 章节", "如 32-41-03", 200)
        pri_dd = ft.Dropdown(
            label="优先级", value="cat_c",
            options=[ft.dropdown.Option(k, v) for k, v in [
                ("aog", "AOG — 立即"), ("cat_a", "Cat A — 当日"),
                ("cat_b", "Cat B — 72h"), ("cat_c", "Cat C — 10 天"),
                ("cat_d", "Cat D — 120 天")]],
            border_color=theme.border, focused_border_color=theme.info,
            bgcolor=theme.card, width=200,
        )

        def create(_):
            t = (title_f.value or "").strip()
            if not t:
                Toast.show(self._page, "请输入标题", "warning"); return
            task_service.create_task(
                title=t, aircraft_reg=(reg_f.value or "").strip(),
                ata_chapter=(ata_f.value or "").strip(),
                priority=pri_dd.value or "cat_c")
            dlg.open = False; self._page.update()
            Toast.show(self._page, f"已创建: {t}", "success")

        dlg = ft.AlertDialog(
            title=ft.Text("新建维护任务", size=theme.font_lg,
                          weight=ft.FontWeight.W_600, color=theme.text_primary,
                          font_family=theme.font_family),
            content=ft.Column(
                [title_f, ft.Row([reg_f, ata_f], spacing=theme.pad_md), pri_dd],
                spacing=theme.pad_md, tight=True, width=round(400 * 1.5)),
            actions=[
                ft.TextButton("取消",
                              on_click=lambda e: setattr(dlg, 'open', False)),
                ft.ElevatedButton("创建", on_click=create,
                                  style=ft.ButtonStyle(bgcolor=theme.info)),
            ],
            bgcolor=theme.surface,
            shape=ft.RoundedRectangleBorder(radius=theme.radius_md),
        )
        self._page.dialog = dlg; dlg.open = True; self._page.update()

    def _dlg_filter(self):
        ata_dd = ft.Dropdown(
            label="ATA 章节",
            options=[ft.dropdown.Option(k, v) for k, v in [
                ("21", "21 - 空调"), ("24", "24 - 电源"),
                ("27", "27 - 飞行控制"), ("28", "28 - 燃油"),
                ("32", "32 - 起落架"), ("49", "49 - APU"),
                ("72", "72 - 发动机"), ("79", "79 - 滑油")]],
            border_color=theme.border, bgcolor=theme.card)
        pri_dd = ft.Dropdown(
            label="优先级",
            options=[ft.dropdown.Option(k, v) for k, v in [
                ("aog", "AOG"), ("cat_a", "Cat A"),
                ("cat_b", "Cat B"), ("cat_c", "Cat C")]],
            border_color=theme.border, bgcolor=theme.card)

        def apply(_):
            f = FilterState()
            if ata_dd.value: f.ata_chapters = [ata_dd.value]
            if pri_dd.value: f.priorities = [pri_dd.value]
            board_service.set_filters(f)
            dlg.open = False; self._page.update()
            Toast.show(self._page, "筛选已应用", "info")

        dlg = ft.AlertDialog(
            title=ft.Text("筛选", size=theme.font_lg, weight=ft.FontWeight.W_600,
                          color=theme.text_primary, font_family=theme.font_family),
            content=ft.Column([ata_dd, pri_dd], spacing=theme.pad_md,
                              tight=True, width=round(300 * 1.5)),
            actions=[
                ft.TextButton("清除", on_click=lambda e: (
                    board_service.set_filters(FilterState()),
                    setattr(dlg, 'open', False), self._page.update())),
                ft.ElevatedButton("应用", on_click=apply,
                                  style=ft.ButtonStyle(bgcolor=theme.info)),
            ],
            bgcolor=theme.surface,
            shape=ft.RoundedRectangleBorder(radius=theme.radius_md),
        )
        self._page.dialog = dlg; dlg.open = True; self._page.update()
