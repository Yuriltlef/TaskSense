"""看板控制器 — UI ↔ Core 桥梁."""

from typing import Optional, Callable

from app.core.models.kanban import BoardState, FilterState
from app.core.models.task import Task
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
        self._on_board_changed: Optional[Callable] = None

        # 订阅状态变更
        state.subscribe(self._on_state_changed)

    @property
    def on_board_changed(self) -> Optional[Callable]:
        return self._on_board_changed

    @on_board_changed.setter
    def on_board_changed(self, callback: Callable):
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

    # load_demo_data() 已废弃—移至 scripts/legacy_demo_data.py
    # 数据统一由 data/board_state.json 管理
