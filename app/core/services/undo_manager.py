"""撤销/重做管理器 — Command 模式。

用法:
    mgr = UndoManager()

    # 记录操作
    mgr.push(
        description="移动 起落架排故 → triage",
        undo_fn=lambda: state.move_task(tid, "backlog"),
        redo_fn=lambda: state.move_task(tid, "triage"),
        group_id=None,
    )

    # 撤销/重做
    mgr.undo()  # Ctrl+Z
    mgr.redo()  # Ctrl+Y / Ctrl+Shift+Z

分组（批量操作）:
    mgr.begin_group("AI 分类 3 个任务")
    mgr.push(...)  # 自动归组
    mgr.push(...)
    mgr.end_group()  # undo 时一次撤销整组
"""

import threading
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class _Command:
    """单条可撤销命令。"""
    description: str
    undo_fn: Callable[[], None]
    redo_fn: Callable[[], None]
    group_id: Optional[str] = None


class UndoManager:
    """撤销/重做管理器（单例，线程安全）。"""

    _instance: Optional["UndoManager"] = None
    MAX_STACK = 200  # 最多保留 200 步

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._lock = threading.Lock()
        self._undo_stack: list[_Command] = []
        self._redo_stack: list[_Command] = []
        self._group: list[_Command] = []
        self._group_id: Optional[str] = None
        self._group_desc: str = ""
        self._on_change: Optional[Callable] = None

    # ── 公开 API ──

    @property
    def can_undo(self) -> bool:
        with self._lock:
            return len(self._undo_stack) > 0

    @property
    def can_redo(self) -> bool:
        with self._lock:
            return len(self._redo_stack) > 0

    @property
    def undo_description(self) -> str:
        with self._lock:
            if self._undo_stack:
                return self._undo_stack[-1].description
            return ""

    @property
    def redo_description(self) -> str:
        with self._lock:
            if self._redo_stack:
                return self._redo_stack[-1].description
            return ""

    def push(self, description: str, undo_fn: Callable, redo_fn: Callable,
             group_id: Optional[str] = None):
        """记录一条可撤销操作。如果正在分组中，自动归入当前组。"""
        cmd = _Command(description, undo_fn, redo_fn,
                       group_id or self._group_id)

        with self._lock:
            if self._group_id:
                self._group.append(cmd)
            else:
                self._undo_stack.append(cmd)
                if len(self._undo_stack) > self.MAX_STACK:
                    self._undo_stack = self._undo_stack[-self.MAX_STACK:]

        # 新操作使 redo 栈失效
        with self._lock:
            self._redo_stack.clear()

        self._notify()

    def begin_group(self, description: str):
        """开始分组——后续 push 自动归入此组。"""
        import uuid
        with self._lock:
            self._group_id = uuid.uuid4().hex[:8]
            self._group_desc = description
            self._group = []

    def end_group(self):
        """结束分组——将组内命令合并为一个可撤销单元。"""
        with self._lock:
            if not self._group_id or not self._group:
                self._group_id = None
                self._group = []
                return

            group = list(self._group)
            desc = self._group_desc

            def undo_all():
                for cmd in reversed(group):
                    cmd.undo_fn()

            def redo_all():
                for cmd in group:
                    cmd.redo_fn()

            self._undo_stack.append(_Command(desc, undo_all, redo_all))
            if len(self._undo_stack) > self.MAX_STACK:
                self._undo_stack = self._undo_stack[-self.MAX_STACK:]

            self._group_id = None
            self._group = []
            self._redo_stack.clear()

        self._notify()

    def undo(self) -> bool:
        """执行一次撤销。返回是否成功。"""
        with self._lock:
            if not self._undo_stack:
                return False
            cmd = self._undo_stack.pop()

        UndoManager._replaying = True
        try:
            cmd.undo_fn()
            with self._lock:
                self._redo_stack.append(cmd)
            self._notify()
            return True
        except Exception as e:
            from app.core.logging import log
            log.warn("undo", f"undo failed: {e}")
            return False
        finally:
            UndoManager._replaying = False

    def redo(self) -> bool:
        """执行一次重做。返回是否成功。"""
        with self._lock:
            if not self._redo_stack:
                return False
            cmd = self._redo_stack.pop()

        UndoManager._replaying = True
        try:
            cmd.redo_fn()
            with self._lock:
                self._undo_stack.append(cmd)
            self._notify()
            return True
        except Exception as e:
            from app.core.logging import log
            log.warn("undo", f"redo failed: {e}")
            return False
        finally:
            UndoManager._replaying = False

    _replaying = False  # 撤销/重做执行中——禁止重复记录

    def clear(self):
        """清空所有历史。"""
        with self._lock:
            self._undo_stack.clear()
            self._redo_stack.clear()
            self._group = []
            self._group_id = None
        self._notify()

    def set_on_change(self, callback: Callable):
        self._on_change = callback

    # ── 内部 ──

    def _notify(self):
        if self._on_change:
            try:
                self._on_change()
            except Exception:
                pass

    @classmethod
    def reset(cls):
        """重置单例（测试用）。"""
        cls._instance = None


# 全局单例
undo_manager = UndoManager()
