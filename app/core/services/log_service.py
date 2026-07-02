"""操作日志服务。

记录所有看板操作的审计日志，持久化到 JSON 文件。
"""

import json
import os
import threading
import uuid
from datetime import datetime, date
from typing import Optional


class _LogEncoder(json.JSONEncoder):
    """处理 datetime / date 等不可直接序列化的类型。"""
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if hasattr(obj, 'value'):  # Enum
            return obj.value
        return str(obj)

from app.core.models.log_entry import LogEntry, LogType


class LogService:
    """日志服务（单例）。"""

    _instance: Optional["LogService"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._logs: list[LogEntry] = []
        self._path: str = ""
        self._lock = threading.Lock()
        self._max_memory_logs: int = 1000
        self._loaded: bool = False

    # ── 加载 / 保存 ──

    def set_path(self, path: str):
        """设置日志文件路径。"""
        if not os.path.isabs(path):
            project_root = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..", "..")
            )
            path = os.path.join(project_root, path)
        self._path = path

    def load(self) -> bool:
        """从文件加载日志。"""
        if not self._path or not os.path.exists(self._path):
            self._loaded = True
            return False
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            with self._lock:
                self._logs = [
                    LogEntry.from_dict(d)
                    for d in data
                ]
            self._loaded = True
            return True
        except Exception as e:
            print(f"[LogService] 加载失败: {e}")
            self._loaded = True
            return False

    def save(self) -> bool:
        """保存日志到文件。"""
        if not self._path:
            return False
        try:
            with self._lock:
                os.makedirs(os.path.dirname(self._path), exist_ok=True)
                data = [e.to_dict() for e in self._logs[-2000:]]  # 只保留最近 2000 条
                with open(self._path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2, cls=_LogEncoder)
            return True
        except Exception as e:
            print(f"[LogService] 保存失败: {e}")
            return False

    # ── 写入 ──

    def log(
        self,
        log_type: LogType,
        task_id: str = "",
        task_title: str = "",
        user: str = "system",
        description: str = "",
        details: Optional[dict] = None,
        previous_state: Optional[dict] = None,
        new_state: Optional[dict] = None,
    ) -> LogEntry:
        """写入一条日志。"""
        self._ensure_loaded()

        entry = LogEntry(
            id=str(uuid.uuid4())[:8],
            timestamp=datetime.now(),
            log_type=log_type,
            task_id=task_id,
            task_title=task_title,
            user=user,
            description=description,
            details=details or {},
            previous_state=previous_state,
            new_state=new_state,
        )

        with self._lock:
            self._logs.append(entry)
            # 内存中保留最近 N 条
            if len(self._logs) > self._max_memory_logs:
                self._logs = self._logs[-self._max_memory_logs:]

        # 异步保存
        threading.Thread(target=self.save, daemon=True).start()
        return entry

    # ── 查询 ──

    def get_logs(
        self,
        task_id: Optional[str] = None,
        log_type: Optional[LogType] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LogEntry]:
        """查询日志。可按任务 ID 和类型过滤。"""
        self._ensure_loaded()
        with self._lock:
            results = list(self._logs)

        if task_id:
            results = [e for e in results if e.task_id == task_id]
        if log_type:
            results = [e for e in results if e.log_type == log_type]

        results.sort(key=lambda e: e.timestamp, reverse=True)
        return results[offset:offset + limit]

    def get_task_history(self, task_id: str) -> list[LogEntry]:
        """获取单个任务的完整操作历史。"""
        return self.get_logs(task_id=task_id, limit=500)

    def get_recent_logs(self, limit: int = 50) -> list[LogEntry]:
        """获取最近日志。"""
        return self.get_logs(limit=limit)

    def get_logs_by_type(self, log_type: LogType, limit: int = 100) -> list[LogEntry]:
        """按类型获取日志。"""
        return self.get_logs(log_type=log_type, limit=limit)

    def search_logs(self, query: str, limit: int = 50) -> list[LogEntry]:
        """全文搜索日志。"""
        self._ensure_loaded()
        q = query.lower()
        with self._lock:
            results = [
                e for e in self._logs
                if q in e.description.lower()
                or q in e.task_title.lower()
                or q in e.task_id.lower()
                or q in e.user.lower()
            ]
        results.sort(key=lambda e: e.timestamp, reverse=True)
        return results[:limit]

    def log_count(self) -> int:
        """日志总数。"""
        self._ensure_loaded()
        with self._lock:
            return len(self._logs)

    def clear(self):
        """清空日志（测试用）。"""
        with self._lock:
            self._logs.clear()

    # ── 内部 ──

    def _ensure_loaded(self):
        """确保已加载。"""
        if not self._loaded:
            self.load()

    @classmethod
    def reset(cls):
        """重置单例（测试用）。"""
        cls._instance = None


# 全局单例
log_service = LogService()
