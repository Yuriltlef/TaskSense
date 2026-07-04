# -*- coding: utf-8 -*-
"""任务注册表 — 线程安全的状态栏任务管理。

被 BoardPage 和多个后台 AI 线程共享访问。
"""

import threading
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class TaskEntry:
    """注册表中的单条任务记录。"""
    id: str
    label: str
    status: str
    type: str                    # "ai_panel" | "report" | "review"
    progress: Optional[float] = None


class TaskRegistry:
    """线程安全的任务注册表。

    维护底部状态栏显示的任务列表。
    AI 命令启动/完成/取消时更新。
    """

    def __init__(self, on_change: Callable[[], None] | None = None):
        self._lock = threading.Lock()
        self._tasks: list[TaskEntry] = []
        self._on_change = on_change

    # ── 公开接口 ──

    def register(self, task_id: str, label: str, status: str,
                 task_type: str, progress: float | None = None):
        """注册或更新一个任务（同 ID 会覆盖）。"""
        entry = TaskEntry(id=task_id, label=label, status=status,
                          type=task_type, progress=progress)
        with self._lock:
            self._tasks = [t for t in self._tasks if t.id != task_id]
            self._tasks.append(entry)
        self._notify()

    def unregister(self, task_id: str):
        """从注册表移除任务。"""
        with self._lock:
            self._tasks = [t for t in self._tasks if t.id != task_id]
        self._notify()

    def update_status(self, task_id: str, status: str,
                      progress: float | None = None):
        """更新任务状态文字和进度（不改变其他字段）。"""
        with self._lock:
            for t in self._tasks:
                if t.id == task_id:
                    t.status = status
                    if progress is not None:
                        t.progress = progress
                    break
        self._notify()

    def find_by_label(self, label: str) -> str | None:
        """根据标签名查找任务 ID，无匹配返回 None。"""
        with self._lock:
            for t in self._tasks:
                if t.label == label:
                    return t.id
        return None

    def get_all(self) -> list[dict]:
        """返回任务列表的快照（供状态栏渲染）。"""
        with self._lock:
            return [
                {"id": t.id, "label": t.label, "status": t.status,
                 "progress": t.progress, "type": t.type}
                for t in self._tasks
            ]

    # ── 内部 ──

    def _notify(self):
        if self._on_change:
            try:
                self._on_change()
            except Exception:
                pass
