"""看板自动流转调度器。

后台线程定期检查任务状态，根据时间/分配/阻塞条件自动推进任务。
"""

import threading
from datetime import datetime
from typing import Optional

from app.core.logging import log


class BoardScheduler:
    """自动流转调度器（单例）。

    定期检查条件并自动推进任务：
    - scheduled → ready：计划开始时间已到且已分配人员
    """

    _instance: Optional["BoardScheduler"] = None

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
        self._interval: float = 10.0  # 检查间隔（秒）
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
        """执行一次检查（供测试或手动触发）。返回变更摘要。"""
        from app.core.state import state
        from app.core.services.task_service import task_service
        from app.core.models.task import TaskStatus

        now = datetime.now()
        summary = {
            "scheduled_to_ready": 0,
            "checked": 0,
        }

        tasks = state.get_all_tasks()
        summary["checked"] = len(tasks)

        for task in tasks:
            # 1. scheduled → ready：计划开始时间已到 + 已分配人员
            if task.status == TaskStatus.SCHEDULED:
                if task.planned_start and task.planned_start <= now:
                    if task.employee_id or task.employee_name:
                        try:
                            task_service.move_task(
                                task.id, "ready", changed_by="system"
                            )
                            summary["scheduled_to_ready"] += 1
                        except Exception as e:
                            log.warn("scheduler", f"scheduled→ready failed: {e}")

        return summary

    # ── 内部 ──

    def _loop(self):
        """后台循环。"""
        while not self._stop_event.is_set():
            try:
                self.tick()
            except Exception as e:
                log.warn("scheduler", f"tick error: {e}")
            self._stop_event.wait(self._interval)

    @classmethod
    def reset(cls):
        """重置单例（测试用）。"""
        if cls._instance:
            cls._instance.stop()
        cls._instance = None


# 全局单例
board_scheduler = BoardScheduler()
