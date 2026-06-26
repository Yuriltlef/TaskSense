"""看板服务 — 看板操作与查询."""

from typing import Optional

from app.core.models.kanban import BoardState, FilterState
from app.core.models.task import Task
from app.core.state import state


class BoardService:
    """看板业务服务。"""

    def __init__(self):
        self.state = state

    def get_board(self) -> BoardState:
        """获取当前看板状态（含筛选）。"""
        return self.state.get_board_state()

    def set_filters(self, filters: FilterState):
        """设置筛选条件。"""
        self.state.set_filters(filters)

    def set_swimlane(self, by: Optional[str]):
        """设置 Swimlane 分组维度。"""
        self.state.set_swimlane(by)

    def search_tasks(self, query: str) -> list[Task]:
        """搜索任务。"""
        if not query:
            return []
        q = query.lower()
        results = []
        for task in self.state.get_all_tasks():
            if (
                q in task.title.lower()
                or q in task.ata_chapter.lower()
                or q in task.aircraft_reg.lower()
                or q in task.fault_code.lower()
                or (task.assignee and q in task.assignee.lower())
            ):
                results.append(task)
        return results

    def reorder_column(self, col_id: str, task_ids: list[str]):
        """列内排序。"""
        self.state.reorder_column(col_id, task_ids)

    def get_fleet_summary(self) -> dict:
        """获取机队摘要。"""
        return self.state.get_fleet_summary()

    def get_stats(self) -> dict:
        """获取看板统计。"""
        return self.state.get_stats()


# 全局实例
board_service = BoardService()
