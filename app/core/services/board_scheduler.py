"""看板时间驱动调度器。

仅处理纯时间触发的业务逻辑，不模拟任何员工操作。

原则：
- 员工接单/提交验收/阻塞 = 真实员工通过 Employee 工作台操作，调度器绝不越权
- 调度器只负责：到期推进/回退（scheduled↔ready）、逾期检测
"""

import threading
from datetime import datetime
from typing import Optional

from app.core.logging import log


class BoardScheduler:
    """时间驱动调度器（单例）。

    纯时间触发的自动化：
    - scheduled → ready：计划开始时间已到 + 已分配人员
    - ready → scheduled：计划开始时间被推迟到未来（重新排程后）
    - 逾期检测：到期未完成的任务记录日志和事件

    明确不做的（属于真实员工操作）：
    - 不自动 accept_task（ready → in_progress）
    - 不自动 submit_task（in_progress → inspection）
    - 不自动 block_task
    - 不自动完成/归档
    """

    _instance: Optional["BoardScheduler"] = None
    _notified_overdue: set[str] = set()  # 已通知逾期的任务 ID，防重复

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._interval: float = 10.0
        self._running: bool = False

    # ── 公开 API ──

    def start(self, interval: float = 10.0):
        """启动调度器。"""
        if self._running:
            return
        self._interval = interval
        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        """停止调度器。"""
        self._running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None

    @staticmethod
    def tick() -> dict:
        """执行一次检查。返回变更摘要。"""
        from app.core.state import state
        from app.core.services.task_service import task_service
        from app.core.models.task import TaskStatus
        from app.core.events import event_bus, EventType, AppEvent
        from app.core.models.log_entry import LogType
        from app.core.services.log_service import log_service

        now = datetime.now()
        summary = {
            "scheduled_to_ready": 0,
            "ready_to_scheduled": 0,
            "new_overdue": 0,
            "checked": 0,
        }

        tasks = state.get_all_tasks()
        summary["checked"] = len(tasks)

        for task in tasks:
            try:
                # ── 1. scheduled → ready：计划开始时间已到 + 已分配人员 ──
                if task.status == TaskStatus.SCHEDULED:
                    if task.planned_start and task.planned_start <= now:
                        if task.employee_id or task.employee_name:
                            task_service.move_task(
                                task.id, "ready", changed_by="system"
                            )
                            summary["scheduled_to_ready"] += 1
                            log.info("scheduler",
                                     f"到期推进 scheduled→ready: {task.id[:8]} "
                                     f"'{task.title[:20]}' "
                                     f"planned={task.planned_start.strftime('%m-%d %H:%M')} "
                                     f"assignee={task.employee_name or task.employee_id}")

                # ── 2. ready → scheduled：计划开始时间被推迟到未来 ──
                elif task.status == TaskStatus.READY:
                    if task.planned_start and task.planned_start > now:
                        task_service.move_task(
                            task.id, "scheduled", changed_by="system"
                        )
                        summary["ready_to_scheduled"] += 1
                        log.info("scheduler",
                                 f"计划推迟 ready→scheduled: {task.id[:8]} "
                                 f"'{task.title[:20]}' "
                                 f"planned={task.planned_start.strftime('%m-%d %H:%M')}")

                # ── 3. 逾期检测：仅通知，不改变任务状态 ──
                if (task.is_overdue
                        and task.status not in (TaskStatus.COMPLETED, TaskStatus.ARCHIVED)
                        and task.id not in BoardScheduler._notified_overdue):
                    BoardScheduler._notified_overdue.add(task.id)
                    summary["new_overdue"] += 1

                    log_service.log(
                        log_type=LogType.SYSTEM_AUTO,
                        task_id=task.id,
                        task_title=task.title,
                        user="system",
                        description=(
                            f"逾期提醒: "
                            f"due={task.due_date.strftime('%m-%d %H:%M') if task.due_date else '?'} "
                            f"status={task.status.value} priority={task.priority.value}"
                        ),
                        details={
                            "status": task.status.value,
                            "due_date": task.due_date.isoformat() if task.due_date else None,
                            "priority": task.priority.value,
                        },
                    )

                    event_bus.emit(AppEvent(
                        type=EventType.TASK_OVERDUE,
                        data={
                            "task_id": task.id,
                            "title": task.title,
                            "due_date": task.due_date.isoformat() if task.due_date else None,
                        },
                    ))
            except Exception as e:
                log.warn("scheduler",
                         f"处理任务 {task.id[:8]} 时出错: {e}")

        return summary

    @classmethod
    def reset(cls):
        """重置单例（测试用）。"""
        if cls._instance:
            cls._instance.stop()
        cls._instance = None
        cls._notified_overdue.clear()

    # ── 内部 ──

    def _loop(self):
        """后台循环。"""
        while not self._stop_event.is_set():
            try:
                self.tick()
            except Exception as e:
                log.warn("scheduler", f"tick异常: {e}")
            self._stop_event.wait(self._interval)


# 全局单例
board_scheduler = BoardScheduler()
