"""看板控制器 — UI ↔ Core 桥梁."""

from typing import Optional

from app.core.events import EventType, event_bus
from app.core.models.kanban import BoardState, FilterState
from app.core.models.task import Task, TaskStatus
from app.core.services.board_service import board_service
from app.core.services.task_service import task_service
from app.core.state import state


class BoardController:
    """看板页面控制器。

    职责：
    1. 持有 UI 层临时状态（选中卡片、加载状态等）
    2. 调用 Service 执行业务操作
    3. 将 Core 数据转换为 UI 可消费格式

    不直接操作 Flet 控件。
    通过回调通知 UI 刷新。
    """

    def __init__(self):
        self.selected_task_id: Optional[str] = None
        self.is_command_bar_open = False
        self.is_side_panel_open = False

        # UI 刷新回调
        self._on_board_changed: Optional[callable] = None

        # 订阅状态变更
        state.subscribe(self._on_state_changed)

    @property
    def on_board_changed(self) -> Optional[callable]:
        return self._on_board_changed

    @on_board_changed.setter
    def on_board_changed(self, callback: callable):
        self._on_board_changed = callback

    def _on_state_changed(self):
        """状态变更 → 通知 UI 刷新。"""
        if self._on_board_changed:
            self._on_board_changed()

    # ═══════════════════════════════════════════════════
    # 看板数据
    # ═══════════════════════════════════════════════════

    def get_board(self) -> BoardState:
        """获取当前看板状态。"""
        return board_service.get_board()

    def get_task(self, task_id: str) -> Optional[Task]:
        return state.get_task(task_id)

    def get_fleet_summary(self) -> dict:
        return board_service.get_fleet_summary()

    # ═══════════════════════════════════════════════════
    # 任务操作
    # ═══════════════════════════════════════════════════

    def create_task(
        self,
        title: str,
        description: str = "",
        aircraft_reg: str = "",
        aircraft_model: str = "",
        ata_chapter: str = "",
        priority: str = "cat_c",
        task_type: str = "troubleshoot",
        **kwargs,
    ) -> Optional[Task]:
        """创建任务。"""
        try:
            return task_service.create_task(
                title=title,
                description=description,
                aircraft_reg=aircraft_reg,
                aircraft_model=aircraft_model,
                ata_chapter=ata_chapter,
                priority=priority,
                task_type=task_type,
                **kwargs,
            )
        except Exception:
            return None

    def move_task(self, task_id: str, to_column: str) -> Optional[Task]:
        """移动任务。"""
        try:
            return task_service.move_task(task_id, to_column)
        except Exception:
            return None

    def delete_task(self, task_id: str) -> bool:
        return task_service.delete_task(task_id)

    def update_task(self, task_id: str, **changes) -> Optional[Task]:
        return task_service.update_task(task_id, **changes)

    # ═══════════════════════════════════════════════════
    # 筛选
    # ═══════════════════════════════════════════════════

    def set_filters(self, filters: FilterState):
        board_service.set_filters(filters)

    def clear_filters(self):
        board_service.set_filters(FilterState())

    def search_tasks(self, query: str) -> list[Task]:
        return board_service.search_tasks(query)

    # ═══════════════════════════════════════════════════
    # 侧面板
    # ═══════════════════════════════════════════════════

    def open_task(self, task_id: str):
        """选中并打开任务详情。"""
        self.selected_task_id = task_id
        self.is_side_panel_open = True

    def close_task(self):
        """关闭任务详情。"""
        self.selected_task_id = None
        self.is_side_panel_open = False

    # ═══════════════════════════════════════════════════
    # 命令面板
    # ═══════════════════════════════════════════════════

    def execute_command(self, action: str, value: str):
        """执行命令面板操作。

        Returns:
            执行结果描述字符串
        """
        if action == "create_task":
            return "create_task_dialog"
        elif action == "create_inspection":
            return "create_inspection_dialog"
        elif action == "generate_report":
            return "report_generated"
        elif action == "check_compliance":
            return "compliance_check"
        elif action == "goto_fleet":
            return "goto_fleet"
        elif action == "filter_ata_32":
            self.set_filters(FilterState(ata_chapters=["32"]))
            return "filtered"
        elif action == "filter_ata_72":
            self.set_filters(FilterState(ata_chapters=["72"]))
            return "filtered"
        elif action == "nl_query":
            # 自然语言查询 → 触发搜索
            results = self.search_tasks(value)
            return f"找到 {len(results)} 个结果"
        return "unknown"

    # ═══════════════════════════════════════════════════
    # 统计
    # ═══════════════════════════════════════════════════

    def get_stats(self) -> dict:
        return board_service.get_stats()

    # ═══════════════════════════════════════════════════
    # 演示数据
    # ═══════════════════════════════════════════════════

    def load_demo_data(self):
        """加载演示数据。"""
        from datetime import datetime, timedelta

        # 演示飞机
        from app.core.models.aircraft import Aircraft, AircraftStatus
        demo_aircraft = [
            Aircraft(
                registration="B-5823", model="737-800", msn="39999",
                status=AircraftStatus.IN_MAINTENANCE, total_hours=28500,
                current_location="Hangar 3", open_defects=3,
            ),
            Aircraft(
                registration="B-2518", model="A320neo", msn="8876",
                status=AircraftStatus.OPERATIONAL, total_hours=12400,
                current_location="Gate A12",
            ),
            Aircraft(
                registration="B-9076", model="A330-300", msn="1503",
                status=AircraftStatus.AOG, total_hours=32100,
                current_location="Hangar 1", open_defects=1,
            ),
        ]
        for ac in demo_aircraft:
            state.add_aircraft(ac)

        # 演示任务
        now = datetime.now()
        demos = [
            ("backlog", "APU 启动时间超限检查", "B-5823", "49-11-01", "aog"),
            ("backlog", "右发滑油消耗率偏高", "B-9076", "79-21-01", "aog"),
            ("backlog", "客舱空调出风口异响", "B-2518", "21-51-01", "cat_c"),
            ("triage", "前起落架转向异响排查", "B-5823", "32-41-03", "cat_a"),
            ("triage", "左发 N1 振动指示异常", "B-9076", "77-11-01", "cat_b"),
            ("scheduled", "A 检 — 飞行控制面检查", "B-5823", "27-10-00", "cat_b"),
            ("scheduled", "发动机滑油更换", "B-2518", "79-00-01", "cat_c"),
            ("ready", "机翼前缘防冰管路测试", "B-5823", "30-11-01", "cat_c"),
            ("ready", "APU 滑油勤务", "B-5823", "49-91-01", "cat_c"),
            ("in_progress", "起落架收放测试", "B-5823", "32-31-01", "cat_b"),
            ("in_progress", "右发燃油滤更换", "B-9076", "73-11-03", "cat_a"),
            ("inspection", "C 检 — 机身结构检查", "B-5823", "53-10-01", "cat_c"),
            ("parts_hold", "左发点火电嘴更换", "B-9076", "74-11-03", "cat_a"),
            ("completed", "驾驶舱仪表灯光检查", "B-2518", "33-11-01", "cat_d"),
            ("completed", "APU 进气门清洁", "B-5823", "49-11-01", "cat_d"),
        ]

        for col_id, title, reg, ata, pri in demos:
            offset = {
                "backlog": 0, "triage": 1, "scheduled": 2,
                "ready": 3, "in_progress": 4, "inspection": 5,
                "parts_hold": 6, "completed": 7,
            }.get(col_id, 0)

            task = self.create_task(
                title=title,
                description=f"{title} — 演示任务。ATA {ata}，飞机 {reg}。",
                aircraft_reg=reg,
                ata_chapter=ata,
                priority=pri,
                task_type="troubleshoot" if "排查" in title or "异常" in title
                else "inspection" if "检查" in title
                else "servicing" if "更换" in title or "勤务" in title
                else "test" if "测试" in title
                else "repair",
                assignee=["张工", "李工", "王工", "赵工"][offset % 4],
                estimated_hours=[2, 4, 6, 1.5, 8][offset % 5],
                due_date=now + timedelta(hours=[2, 4, 24, 48, 72][offset % 5]),
                zone=["710", "420", "310", "510", "110"][offset % 5],
            )

            if task and col_id != "backlog":
                try:
                    # 根据列名推进状态
                    status_order = [
                        "backlog", "triage", "scheduled", "ready",
                        "in_progress", "inspection", "parts_hold", "completed"
                    ]
                    current_idx = status_order.index(col_id)
                    for i in range(1, current_idx + 1):
                        mid_status = status_order[i]
                        if mid_status == "parts_hold":
                            task.parts_available = False
                            task.parts_required = ["PN-32041-05"]
                        task_service.move_task(task.id, mid_status, changed_by="demo")
                except Exception:
                    pass

        # 强制移动已完成的
        moves = [
            (demos[13][0], "completed"),  # demo task 14
            (demos[14][0], "completed"),  # demo task 15
        ]
        # Already handled by the loop above

        return len(demos)
