"""全局状态管理器 — 单一状态树."""

import uuid
from collections import defaultdict
from datetime import datetime
from typing import Callable, Optional

from app.config.constants import DEFAULT_COLUMNS
from app.core.events import AppEvent, EventType, event_bus
from app.core.models.aircraft import Aircraft, AircraftStatus
from app.core.models.kanban import BoardState, ColumnConfig, FilterState
from app.core.models.task import Priority, Task, TaskStatus, TaskType
from app.core.logging import log


class AppState:
    """全局应用状态。

    所有状态变更通过本类方法执行，确保：
    - 变更可追踪
    - 变更后自动通知监听器
    - 事件自动发布到 EventBus
    """

    def __init__(self):
        # ── 看板 ──
        self._columns: dict[str, ColumnConfig] = {}
        self._tasks: dict[str, Task] = {}
        self._task_order: dict[str, list[str]] = defaultdict(list)
        self._filters = FilterState()
        self._swimlane_by: Optional[str] = None

        # ── 飞机 ──
        self._aircraft: dict[str, Aircraft] = {}

        # ── UI 监听器 ──
        self._listeners: list[Callable] = []

        # ── 初始化列 ──
        self._init_columns()

    # ═══════════════════════════════════════════════════
    # 初始化
    # ═══════════════════════════════════════════════════

    def _init_columns(self):
        for col_data in DEFAULT_COLUMNS:
            col = ColumnConfig(
                id=col_data["id"],
                title=col_data["title"],
                wip_limit=col_data["wip_limit"],
                order=col_data["order"],
                visible=col_data["visible"],
            )
            self._columns[col.id] = col
            self._task_order[col.id] = []

    # ═══════════════════════════════════════════════════
    # 监听器
    # ═══════════════════════════════════════════════════

    def subscribe(self, listener: Callable):
        """注册状态变更回调。"""
        self._listeners.append(listener)

    def unsubscribe(self, listener: Callable):
        """移除监听器。"""
        if listener in self._listeners:
            self._listeners.remove(listener)

    def _notify(self):
        """通知所有监听器状态已变更。"""
        for listener in self._listeners:
            try:
                listener()
            except Exception:
                pass

    # ═══════════════════════════════════════════════════
    # 任务 CRUD
    # ═══════════════════════════════════════════════════

    def get_task(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    def get_tasks_by_column(self, col_id: str) -> list[Task]:
        """返回某列的所有任务（按顺序）。"""
        task_ids = self._task_order.get(col_id, [])
        return [self._tasks[tid] for tid in task_ids if tid in self._tasks]

    def get_all_tasks(self) -> list[Task]:
        return list(self._tasks.values())

    def create_task(self, **kwargs) -> Task:
        """创建新任务，自动放入 Backlog 列。"""
        from app.core.models.task import _generate_work_order_id

        task_id = kwargs.pop("id", str(uuid.uuid4())[:8])
        now = datetime.now()

        # 自动生成工卡号
        wo_id = kwargs.pop("work_order_id", None) or _generate_work_order_id()

        task = Task(
            id=task_id,
            work_order_id=wo_id,
            created_at=now,
            updated_at=now,
            status=TaskStatus.BACKLOG,
            **kwargs,
        )
        # 自动从 ata_chapter 提取 ata_section
        if task.ata_chapter and not task.ata_section:
            task.ata_section = task.ata_chapter.split("-")[0]
        self._tasks[task_id] = task
        self._task_order["backlog"].insert(0, task_id)  # 新任务排最前
        log.info("state.create_task", task_id=task_id, wo=wo_id, title=task.title[:30])

        event_bus.emit(AppEvent(
            type=EventType.TASK_CREATED,
            data={"task_id": task_id},
        ))
        # 日志
        from app.core.models.log_entry import LogType
        from app.core.services.log_service import log_service
        log_service.log(
            log_type=LogType.CREATE_TASK,
            task_id=task_id,
            task_title=task.title,
            description=f"创建任务: {task.title}",
        )
        self._notify()
        return task

    def update_task(self, task_id: str, **changes) -> Optional[Task]:
        """更新任务字段。"""
        task = self._tasks.get(task_id)
        if not task:
            return None

        for key, value in changes.items():
            if hasattr(task, key):
                setattr(task, key, value)

        task.updated_at = datetime.now()
        self._tasks[task_id] = task
        log.info("state.update_task", task_id=task_id, fields=",".join(list(changes.keys())[:5]))

        event_bus.emit(AppEvent(
            type=EventType.TASK_UPDATED,
            data={"task_id": task_id, "changes": changes},
        ))
        # 日志
        from app.core.models.log_entry import LogType
        from app.core.services.log_service import log_service
        changed_fields = ", ".join(changes.keys())
        log_service.log(
            log_type=LogType.EDIT_TASK,
            task_id=task_id,
            task_title=task.title,
            description=f"更新字段: {changed_fields}",
            details=changes,
        )
        self._notify()
        return task

    def move_task(self, task_id: str, to_col: str,
                  index: int = -1, changed_by: str = "system") -> Optional[Task]:
        """移动任务到目标列。"""
        task = self._tasks.get(task_id)
        if not task:
            return None

        # 找到当前列
        from_col = None
        for col_id, task_ids in self._task_order.items():
            if task_id in task_ids:
                from_col = col_id
                break

        if from_col is None:
            return None

        # 移除
        self._task_order[from_col].remove(task_id)

        # 添加
        if index < 0 or index >= len(self._task_order[to_col]):
            self._task_order[to_col].append(task_id)
        else:
            self._task_order[to_col].insert(index, task_id)

        # 更新任务状态
        old_status = task.status
        task.transition_to(TaskStatus(to_col), changed_by)
        log.info("state.move_task", task_id=task_id, from_col=from_col, to_col=to_col, by=changed_by)

        event_bus.emit(AppEvent(
            type=EventType.TASK_MOVED,
            data={
                "task_id": task_id,
                "from_col": from_col,
                "to_col": to_col,
                "old_status": old_status.value,
                "new_status": to_col,
            },
        ))
        # 日志
        from app.core.models.log_entry import LogType
        from app.core.services.log_service import log_service
        if changed_by == "system":
            log_type = LogType.SYSTEM_AUTO
        else:
            log_type = LogType.KANBAN_MOVE
        log_service.log(
            log_type=log_type,
            task_id=task_id,
            task_title=task.title,
            user=changed_by,
            description=f"移动: {old_status.value} → {to_col}",
            details={"from_col": from_col, "to_col": to_col},
        )
        self._notify()
        return task

    def delete_task(self, task_id: str) -> bool:
        """删除任务（从所有列移除，不保留数据）。"""
        if task_id not in self._tasks:
            return False

        # 先获取任务信息用于日志
        task = self._tasks[task_id]
        task_title = task.title

        for task_ids in self._task_order.values():
            if task_id in task_ids:
                task_ids.remove(task_id)

        del self._tasks[task_id]

        event_bus.emit(AppEvent(
            type=EventType.TASK_DELETED,
            data={"task_id": task_id},
        ))
        # 日志
        from app.core.models.log_entry import LogType
        from app.core.services.log_service import log_service
        log_service.log(
            log_type=LogType.DELETE_TASK,
            task_id=task_id,
            task_title=task_title,
            description=f"删除任务: {task_title}",
        )
        self._notify()
        return True

    def reorder_column(self, col_id: str, task_ids: list[str]):
        """设置某列的排序。"""
        if col_id in self._task_order:
            self._task_order[col_id] = task_ids
            self._notify()

    # ═══════════════════════════════════════════════════
    # 看板操作
    # ═══════════════════════════════════════════════════

    def get_board_state(self) -> BoardState:
        """获取当前看板状态（经过筛选）。"""
        columns = []
        tasks = {}

        for col in self._columns.values():
            if not col.visible:
                continue
            task_ids = self._task_order.get(col.id, [])
            # 应用筛选
            filtered_ids = self._apply_filters(task_ids)
            col.task_count = len(filtered_ids)
            columns.append(col)
            tasks[col.id] = filtered_ids

        return BoardState(
            columns=sorted(columns, key=lambda c: c.order),
            tasks=tasks,
            filters=self._filters,
            swimlane_by=self._swimlane_by,
        )

    def get_columns(self) -> list[ColumnConfig]:
        return sorted(self._columns.values(), key=lambda c: c.order)

    def set_swimlane(self, by: Optional[str]):
        self._swimlane_by = by
        self._notify()

    # ═══════════════════════════════════════════════════
    # 筛选
    # ═══════════════════════════════════════════════════

    @property
    def filters(self) -> FilterState:
        return self._filters

    def set_filters(self, filters: FilterState):
        self._filters = filters
        event_bus.emit(AppEvent(
            type=EventType.FILTER_CHANGED,
            data={"filters": filters},
        ))
        self._notify()

    def _apply_filters(self, task_ids: list[str]) -> list[str]:
        """应用当前筛选条件。"""
        f = self._filters
        if not f.is_active:
            return task_ids

        result = []
        for tid in task_ids:
            task = self._tasks.get(tid)
            if not task:
                continue
            if not f.show_completed and task.status in (
                TaskStatus.COMPLETED, TaskStatus.ARCHIVED
            ):
                continue
            if f.ata_chapters and task.ata_section not in f.ata_chapters:
                continue
            if f.aircraft_regs and task.aircraft_reg not in f.aircraft_regs:
                continue
            if f.priorities and task.priority.value not in f.priorities:
                continue
            if f.task_types and task.task_type.value not in f.task_types:
                continue
            if f.assignees and task.assignee not in f.assignees:
                continue
            if f.search_query:
                q = f.search_query.lower()
                if not (
                    q in task.title.lower()
                    or q in task.ata_chapter.lower()
                    or q in task.aircraft_reg.lower()
                    or q in (task.assignee or "").lower()
                ):
                    continue
            result.append(tid)
        return result

    # ═══════════════════════════════════════════════════
    # 飞机管理
    # ═══════════════════════════════════════════════════

    def get_aircraft(self, reg: str) -> Optional[Aircraft]:
        return self._aircraft.get(reg)

    def get_all_aircraft(self) -> list[Aircraft]:
        return list(self._aircraft.values())

    def add_aircraft(self, aircraft: Aircraft):
        self._aircraft[aircraft.registration] = aircraft
        self._notify()

    def get_fleet_summary(self) -> dict:
        """机队状态摘要。"""
        summary = {
            "total": len(self._aircraft),
            "operational": 0,
            "in_maintenance": 0,
            "aog": 0,
            "stored": 0,
            "total_open_defects": 0,
            "total_overdue": 0,
        }
        for ac in self._aircraft.values():
            if ac.status == AircraftStatus.OPERATIONAL:
                summary["operational"] += 1
            elif ac.status == AircraftStatus.IN_MAINTENANCE:
                summary["in_maintenance"] += 1
            elif ac.status == AircraftStatus.AOG:
                summary["aog"] += 1
            else:
                summary["stored"] += 1
            summary["total_open_defects"] += ac.open_defects
            summary["total_overdue"] += ac.overdue_tasks_count
        return summary

    # ═══════════════════════════════════════════════════
    # 统计
    # ═══════════════════════════════════════════════════

    def get_stats(self) -> dict:
        """看板统计。"""
        stats = {}
        for col_id in self._task_order:
            count = len(self._task_order[col_id])
            stats[col_id] = count
        stats["total"] = len(self._tasks)
        stats["overdue"] = sum(1 for t in self._tasks.values() if t.is_overdue)
        stats["aog_count"] = sum(
            1 for t in self._tasks.values()
            if t.priority == Priority.AOG
            and t.status not in (TaskStatus.COMPLETED, TaskStatus.ARCHIVED)
        )
        return stats

    # ═══════════════════════════════════════════════════
    # 序列化 / 持久化
    # ═══════════════════════════════════════════════════

    def to_dict(self) -> dict:
        """将完整状态序列化为字典。"""
        return {
            "columns": {
                cid: {
                    "id": col.id,
                    "title": col.title,
                    "wip_limit": col.wip_limit,
                    "order": col.order,
                    "visible": col.visible,
                }
                for cid, col in self._columns.items()
            },
            "tasks": {tid: t.to_dict() for tid, t in self._tasks.items()},
            "task_order": {cid: list(ids) for cid, ids in self._task_order.items()},
            "aircraft": [
                {
                    "registration": ac.registration,
                    "model": ac.model,
                    "msn": ac.msn,
                    "status": ac.status.value,
                    "total_hours": ac.total_hours,
                    "total_cycles": ac.total_cycles,
                    "current_location": ac.current_location,
                    "open_defects": ac.open_defects,
                    "due_tasks_count": ac.due_tasks_count,
                    "overdue_tasks_count": ac.overdue_tasks_count,
                }
                for ac in self._aircraft.values()
            ],
        }

    def load_from_dict(self, data: dict):
        """从字典恢复状态。"""
        # 恢复列
        for col_id, col_data in data.get("columns", {}).items():
            if col_id in self._columns:
                self._columns[col_id].title = col_data.get("title", col_id)
                self._columns[col_id].wip_limit = col_data.get("wip_limit")
                self._columns[col_id].order = col_data.get("order", 0)
                self._columns[col_id].visible = col_data.get("visible", True)

        # 恢复任务
        self._tasks.clear()
        self._task_order.clear()
        for col_id in self._columns:
            self._task_order[col_id] = []

        for tid, tdict in data.get("tasks", {}).items():
            task = Task.from_dict(tdict)
            self._tasks[tid] = task

        for col_id, task_ids in data.get("task_order", {}).items():
            if col_id in self._task_order:
                self._task_order[col_id] = [
                    tid for tid in task_ids if tid in self._tasks
                ]

        # 恢复飞机
        self._aircraft.clear()
        for ac_data in data.get("aircraft", []):
            ac = Aircraft(
                registration=ac_data["registration"],
                model=ac_data.get("model", ""),
                msn=ac_data.get("msn", ""),
                status=AircraftStatus(ac_data.get("status", "operational")),
                total_hours=ac_data.get("total_hours", 0.0),
                total_cycles=ac_data.get("total_cycles", 0),
                current_location=ac_data.get("current_location", ""),
                open_defects=ac_data.get("open_defects", 0),
                due_tasks_count=ac_data.get("due_tasks_count", 0),
                overdue_tasks_count=ac_data.get("overdue_tasks_count", 0),
            )
            self._aircraft[ac.registration] = ac

        self._notify()


# 全局状态实例
state = AppState()
