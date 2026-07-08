"""状态持久化服务。

将 AppState 序列化为 JSON 文件，支持启动加载和自动保存。
支持 filelock 跨进程安全读写 + mtime 外部变更检测。
"""

import json
import os
import threading
from typing import Optional

from filelock import FileLock, Timeout as FileLockTimeout

from app.core.events import event_bus, EventType


class PersistenceService:
    """状态持久化（单例）。"""

    _instance: Optional["PersistenceService"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._path: str = ""
        self._dirty = False
        self._lock = threading.Lock()
        self._save_timer: Optional[threading.Timer] = None
        self._debounce_seconds: float = 5.0
        self._auto_save_enabled: bool = True
        self._running: bool = False
        self._watch_thread: Optional[threading.Thread] = None
        self._file_lock: Optional[FileLock] = None
        self._last_file_mtime: float = 0.0

    # ── 公开 API ──

    def set_path(self, path: str):
        """设置持久化文件路径。"""
        if not os.path.isabs(path):
            # app/core/services/ → ../../.. → 项目根
            project_root = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..", "..")
            )
            path = os.path.join(project_root, path)
        self._path = path
        # 创建跨进程文件锁
        self._file_lock = FileLock(path + ".lock", timeout=5.0)

    def save(self) -> bool:
        """立即保存当前状态到文件（跨进程 filelock 保护）。

        """
        if not self._path:
            return False
        try:
            from app.core.state import state
            data = state.to_dict()
            with self._lock:
                if self._file_lock:
                    self._file_lock.acquire(poll_interval=0.1)
                try:
                    os.makedirs(os.path.dirname(self._path), exist_ok=True)
                    with open(self._path, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    self._dirty = False
                finally:
                    if self._file_lock:
                        self._file_lock.release()
            try:
                self._last_file_mtime = os.path.getmtime(self._path)
            except OSError:
                pass
            return True
        except FileLockTimeout:
            print("[PersistenceService] 保存超时：无法获取文件锁")
            return False
        except Exception as e:
            print(f"[PersistenceService] 保存失败: {e}")
            return False

    def load(self) -> bool:
        """从文件加载状态到 AppState（跨进程 filelock 保护）。"""
        if not self._path or not os.path.exists(self._path):
            return False
        try:
            # 跨进程锁
            if self._file_lock:
                self._file_lock.acquire(poll_interval=0.1)
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                from app.core.state import state
                state.load_from_dict(data)
                self._dirty = False
            finally:
                if self._file_lock:
                    self._file_lock.release()
            # 记录 mtime
            try:
                self._last_file_mtime = os.path.getmtime(self._path)
            except OSError:
                pass
            return True
        except FileLockTimeout:
            print("[PersistenceService] 加载超时：无法获取文件锁")
            return False
        except Exception as e:
            print(f"[PersistenceService] 加载失败: {e}")
            return False

    def mark_dirty(self):
        """标记状态已变更，将触发延迟保存。"""
        self._dirty = True
        if self._auto_save_enabled:
            self._schedule_save()

    def start_auto_save(self, debounce_seconds: float = 5.0):
        """启动自动保存（通过 EventBus 监听状态变更）。"""
        self._debounce_seconds = debounce_seconds
        self._auto_save_enabled = True

        # 防止重复订阅
        if getattr(self, '_subscribed', False):
            return
        self._subscribed = True

        for event_type in (
            EventType.TASK_CREATED, EventType.TASK_MOVED,
            EventType.TASK_UPDATED, EventType.TASK_DELETED,
            EventType.BOARD_CHANGED, EventType.FILTER_CHANGED,
        ):
            event_bus.on(event_type, lambda e, self=self: self.mark_dirty())

    def stop_auto_save(self):
        """停止自动保存。"""
        self._auto_save_enabled = False
        if self._save_timer:
            self._save_timer.cancel()
            self._save_timer = None

    def save_if_dirty(self) -> bool:
        """如果有未保存的变更，立即保存。"""
        if self._dirty:
            return self.save()
        return False

    # ── 外部变更检测 ──

    def has_external_changes(self) -> bool:
        """检测文件是否被外部进程修改。"""
        try:
            current = os.path.getmtime(self._path)
        except OSError:
            return False
        return current != self._last_file_mtime

    def reload_if_changed(self) -> bool:
        """如果检测到外部变更，自动重新加载。返回 True 表示已重新加载。"""
        if self.has_external_changes():
            return self.load()
        return False

    # ── 内部 ──

    def _schedule_save(self):
        """延迟保存（防抖）。"""
        if self._save_timer:
            self._save_timer.cancel()
        self._save_timer = threading.Timer(self._debounce_seconds, self._do_save)
        self._save_timer.daemon = True
        self._save_timer.start()

    def _do_save(self):
        """执行实际保存。"""
        self.save()

    @classmethod
    def reset(cls):
        """重置单例（测试用）。"""
        cls._instance = None


# 全局单例
persistence_service = PersistenceService()
