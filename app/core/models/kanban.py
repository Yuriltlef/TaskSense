"""看板状态模型."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ColumnConfig:
    """看板列配置。"""
    id: str
    title: str
    wip_limit: Optional[int] = None
    order: int = 0
    visible: bool = True

    @property
    def task_count(self) -> int:
        """该列任务数（由 BoardState 设置）。"""
        return getattr(self, "_task_count", 0)

    @task_count.setter
    def task_count(self, value: int):
        self._task_count = value

    @property
    def wip_exceeded(self) -> bool:
        """WIP 是否超限（≥ 上限即视为超限，与 validators 保持一致）。"""
        if self.wip_limit is None:
            return False
        return self.task_count >= self.wip_limit

    @property
    def wip_percentage(self) -> float:
        """WIP 占用百分比。"""
        if self.wip_limit is None or self.wip_limit == 0:
            return 0.0
        return min(self.task_count / self.wip_limit, 1.0)


@dataclass
class FilterState:
    """看板筛选条件。"""
    search_query: str = ""
    ata_chapters: list[str] = field(default_factory=list)
    aircraft_regs: list[str] = field(default_factory=list)
    priorities: list[str] = field(default_factory=list)
    task_types: list[str] = field(default_factory=list)
    assignees: list[str] = field(default_factory=list)
    employee_ids: list[str] = field(default_factory=list)
    statuses: list[str] = field(default_factory=list)
    start_date_from: Optional[datetime] = None
    start_date_to: Optional[datetime] = None
    due_date_from: Optional[datetime] = None
    due_date_to: Optional[datetime] = None
    show_completed: bool = False

    @property
    def is_active(self) -> bool:
        """是否有任何筛选条件激活。"""
        return bool(
            self.search_query
            or self.ata_chapters
            or self.aircraft_regs
            or self.priorities
            or self.task_types
            or self.assignees
            or self.employee_ids
            or self.statuses
            or self.start_date_from
            or self.start_date_to
            or self.due_date_from
            or self.due_date_to
        )

    @property
    def active_filter_count(self) -> int:
        """激活的筛选器数量。"""
        count = 0
        if self.search_query: count += 1
        if self.ata_chapters: count += 1
        if self.aircraft_regs: count += 1
        if self.priorities: count += 1
        if self.task_types: count += 1
        if self.assignees: count += 1
        if self.employee_ids: count += 1
        if self.statuses: count += 1
        if self.start_date_from or self.start_date_to: count += 1
        if self.due_date_from or self.due_date_to: count += 1
        return count

    @property
    def summary(self) -> list[str]:
        """人类可读的筛选条件摘要列表。"""
        items = []
        if self.search_query:
            items.append(f"搜索: {self.search_query}")
        if self.ata_chapters:
            items.append(f"ATA: {', '.join(self.ata_chapters)}")
        if self.priorities:
            labels = {"aog": "AOG", "cat_a": "Cat A", "cat_b": "Cat B", "cat_c": "Cat C"}
            items.append(f"优先级: {', '.join(labels.get(p, p) for p in self.priorities)}")
        if self.task_types:
            items.append(f"类型: {', '.join(self.task_types)}")
        if self.assignees:
            items.append(f"负责人: {', '.join(self.assignees)}")
        if self.employee_ids:
            items.append(f"员工: {', '.join(self.employee_ids)}")
        if self.statuses:
            items.append(f"状态: {', '.join(self.statuses)}")
        if self.start_date_from:
            items.append(f"开始≥{self.start_date_from.strftime('%m-%d')}")
        if self.start_date_to:
            items.append(f"开始≤{self.start_date_to.strftime('%m-%d')}")
        if self.due_date_from:
            items.append(f"截止≥{self.due_date_from.strftime('%m-%d')}")
        if self.due_date_to:
            items.append(f"截止≤{self.due_date_to.strftime('%m-%d')}")
        return items


@dataclass
class BoardState:
    """看板完整状态。"""
    columns: list[ColumnConfig] = field(default_factory=list)
    tasks: dict[str, list[str]] = field(default_factory=dict)  # col_id → [task_id, ...]
    filters: FilterState = field(default_factory=FilterState)
    swimlane_by: Optional[str] = None  # "ata" | "aircraft" | "team" | None

    def get_task_ids(self, col_id: str) -> list[str]:
        """获取某列的所有任务ID。"""
        return self.tasks.get(col_id, [])

    def get_task_count(self, col_id: str) -> int:
        """获取某列的任务数量。"""
        return len(self.tasks.get(col_id, []))

    def task_column(self, task_id: str) -> Optional[str]:
        """查找任务所在的列。"""
        for col_id, task_ids in self.tasks.items():
            if task_id in task_ids:
                return col_id
        return None
