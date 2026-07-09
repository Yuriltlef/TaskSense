"""状态持久化服务 — SQLite 存储。

替换旧 JSON 文件方案，改用 SQLite：
- 原子写入（不会因崩溃损坏数据）
- 并发安全（SQLite WAL 模式）
- 日志可结构化查询
- 无需 filelock 依赖
"""

import json
import os
import sqlite3
import threading
from datetime import datetime
from typing import Optional


class PersistenceService:
    """状态持久化（单例，SQLite 后端）。"""

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
        self._db_path: str = ""
        self._dirty = False
        self._lock = threading.Lock()
        self._save_timer: Optional[threading.Timer] = None
        self._debounce_seconds: float = 5.0
        self._auto_save_enabled: bool = True
        self._running: bool = False

    # ── 公开 API ──

    def set_path(self, path: str):
        """设置 SQLite 数据库文件路径。"""
        if not os.path.isabs(path):
            project_root = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..", "..")
            )
            path = os.path.join(project_root, path)
        self._db_path = path
        self._init_db()

    def save(self) -> bool:
        """将当前状态写入 SQLite。"""
        if not self._db_path:
            return False
        try:
            from app.core.state import state
            data = state.to_dict()
            with self._lock:
                self._write_state(data)
                self._dirty = False
            return True
        except Exception as e:
            print(f"[PersistenceService] 保存失败: {e}")
            return False

    def load(self) -> bool:
        """从 SQLite 加载状态到 AppState。"""
        if not self._db_path or not os.path.exists(self._db_path):
            return False
        try:
            with self._lock:
                data = self._read_state()
            if data is None:
                return False
            from app.core.state import state
            state.load_from_dict(data)
            self._dirty = False
            return True
        except Exception as e:
            print(f"[PersistenceService] 加载失败: {e}")
            return False

    def mark_dirty(self):
        """标记状态已变更，触发延迟保存。"""
        self._dirty = True
        if self._auto_save_enabled:
            self._schedule_save()

    def start_auto_save(self, debounce_seconds: float = 5.0):
        """启动自动保存（EventBus 监听状态变更）。"""
        self._debounce_seconds = debounce_seconds
        self._auto_save_enabled = True

        if getattr(self, '_subscribed', False):
            return
        self._subscribed = True

        from app.core.events import event_bus, EventType
        for event_type in (
            EventType.TASK_CREATED, EventType.TASK_MOVED,
            EventType.TASK_UPDATED, EventType.TASK_DELETED,
            EventType.BOARD_CHANGED, EventType.FILTER_CHANGED,
        ):
            event_bus.on(event_type, lambda e, s=self: s.mark_dirty())

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

    # ── 数据迁移 ──

    def migrate_from_json(self, json_path: str) -> bool:
        """从旧 JSON 文件迁移数据到 SQLite（一次性）。"""
        if not os.path.exists(json_path):
            print(f"[PersistenceService] 源文件不存在: {json_path}")
            return False
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._write_state(data)
            print(f"[PersistenceService] 迁移完成: {json_path} → {self._db_path}")
            return True
        except Exception as e:
            print(f"[PersistenceService] 迁移失败: {e}")
            return False

    # ── SQLite 底层 ──

    def _get_conn(self) -> sqlite3.Connection:
        """获取数据库连接（WAL 模式，支持并发读）。"""
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        conn = sqlite3.connect(self._db_path, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """初始化数据库表结构。"""
        conn = self._get_conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    work_order_id TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'backlog',
                    priority TEXT NOT NULL DEFAULT 'cat_c',
                    task_type TEXT NOT NULL DEFAULT 'troubleshoot',
                    aircraft_reg TEXT DEFAULT '',
                    aircraft_model TEXT DEFAULT '',
                    ata_chapter TEXT DEFAULT '',
                    ata_section TEXT DEFAULT '',
                    assignee TEXT DEFAULT '',
                    employee_id TEXT DEFAULT '',
                    employee_name TEXT DEFAULT '',
                    estimated_hours REAL DEFAULT 0,
                    actual_hours REAL DEFAULT 0,
                    due_date TEXT,
                    planned_start TEXT,
                    planned_end TEXT,
                    zone TEXT DEFAULT '',
                    fault_code TEXT DEFAULT '',
                    is_blocked INTEGER DEFAULT 0,
                    block_reason TEXT DEFAULT '',
                    is_rii INTEGER DEFAULT 0,
                    inspector TEXT DEFAULT '',
                    created_by TEXT DEFAULT 'user',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    ai_proposed INTEGER DEFAULT 0,
                    ai_priority TEXT,
                    checklist_json TEXT DEFAULT '[]',
                    ai_suggestions_json TEXT DEFAULT '[]',
                    ad_numbers_json TEXT DEFAULT '[]',
                    sb_numbers_json TEXT DEFAULT '[]',
                    mel_item TEXT DEFAULT '',
                    parts_available INTEGER DEFAULT 1,
                    shift_handover_log TEXT DEFAULT '',
                    ai_acceptance_recommendation TEXT,
                    ai_acceptance_reason TEXT
                );

                CREATE TABLE IF NOT EXISTS task_order (
                    col_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    PRIMARY KEY (col_id, task_id),
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS columns_config (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    wip_limit INTEGER,
                    ord INTEGER DEFAULT 0,
                    visible INTEGER DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS aircraft (
                    registration TEXT PRIMARY KEY,
                    model TEXT DEFAULT '',
                    msn TEXT DEFAULT '',
                    status TEXT DEFAULT 'operational',
                    total_hours REAL DEFAULT 0,
                    total_cycles INTEGER DEFAULT 0,
                    current_location TEXT DEFAULT '',
                    open_defects INTEGER DEFAULT 0,
                    due_tasks_count INTEGER DEFAULT 0,
                    overdue_tasks_count INTEGER DEFAULT 0
                );
            """)
            conn.commit()
        finally:
            conn.close()

    def _write_state(self, data: dict):
        """将完整状态字典写入 SQLite（事务性）。"""
        conn = self._get_conn()
        try:
            with conn:
                # ── 列配置 ──
                conn.execute("DELETE FROM columns_config")
                for col_id, col in data.get("columns", {}).items():
                    conn.execute(
                        "INSERT OR REPLACE INTO columns_config (id, title, wip_limit, ord, visible) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (col_id, col.get("title", ""), col.get("wip_limit"),
                         col.get("order", 0), 1 if col.get("visible", True) else 0)
                    )

                # ── 任务 ──
                conn.execute("DELETE FROM tasks")
                tasks_data = data.get("tasks", {})
                for tid, t in tasks_data.items():
                    self._insert_task(conn, tid, t)

                # ── 任务排序 ──
                conn.execute("DELETE FROM task_order")
                for col_id, task_ids in data.get("task_order", {}).items():
                    for idx, tid in enumerate(task_ids):
                        if tid in tasks_data:
                            conn.execute(
                                "INSERT INTO task_order (col_id, task_id, position) "
                                "VALUES (?, ?, ?)",
                                (col_id, tid, idx)
                            )

                # ── 飞机 ──
                conn.execute("DELETE FROM aircraft")
                for ac in data.get("aircraft", []):
                    conn.execute(
                        "INSERT OR REPLACE INTO aircraft "
                        "(registration, model, msn, status, total_hours, "
                        " total_cycles, current_location, open_defects, "
                        " due_tasks_count, overdue_tasks_count) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (ac.get("registration", ""), ac.get("model", ""),
                         ac.get("msn", ""), ac.get("status", "operational"),
                         ac.get("total_hours", 0), ac.get("total_cycles", 0),
                         ac.get("current_location", ""), ac.get("open_defects", 0),
                         ac.get("due_tasks_count", 0), ac.get("overdue_tasks_count", 0))
                    )
        finally:
            conn.close()

    @staticmethod
    def _insert_task(conn, tid: str, t: dict):
        """插入单条任务记录。JSON 数组字段序列化为 TEXT。"""
        conn.execute(
            """INSERT INTO tasks (
                id, work_order_id, title, description, status, priority, task_type,
                aircraft_reg, aircraft_model, ata_chapter, ata_section,
                assignee, employee_id, employee_name,
                estimated_hours, actual_hours, due_date, planned_start, planned_end,
                zone, fault_code, is_blocked, block_reason, is_rii, inspector,
                created_by, created_at, updated_at,
                ai_proposed, ai_priority,
                checklist_json, ai_suggestions_json,
                ad_numbers_json, sb_numbers_json,
                mel_item, parts_available,
                shift_handover_log, ai_acceptance_recommendation, ai_acceptance_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                tid,
                t.get("work_order_id", ""),
                t.get("title", ""),
                t.get("description", ""),
                t.get("status", "backlog"),
                t.get("priority", "cat_c"),
                t.get("task_type", "troubleshoot"),
                t.get("aircraft_reg", ""),
                t.get("aircraft_model", ""),
                t.get("ata_chapter", ""),
                t.get("ata_section", ""),
                t.get("assignee", ""),
                t.get("employee_id", ""),
                t.get("employee_name", ""),
                t.get("estimated_hours", 0),
                t.get("actual_hours", 0),
                t.get("due_date"),
                t.get("planned_start"),
                t.get("planned_end"),
                t.get("zone", ""),
                t.get("fault_code", ""),
                1 if t.get("is_blocked") else 0,
                t.get("block_reason", ""),
                1 if t.get("is_rii") else 0,
                t.get("inspector", ""),
                t.get("created_by", "user"),
                t.get("created_at", datetime.now().isoformat()),
                t.get("updated_at", datetime.now().isoformat()),
                1 if t.get("ai_proposed") else 0,
                t.get("ai_priority"),
                json.dumps(t.get("checklist", []), ensure_ascii=False),
                json.dumps(t.get("ai_suggestions", []), ensure_ascii=False),
                json.dumps(t.get("ad_numbers", []), ensure_ascii=False),
                json.dumps(t.get("sb_numbers", []), ensure_ascii=False),
                t.get("mel_item", ""),
                1 if t.get("parts_available", True) else 0,
                t.get("shift_handover_log", ""),
                t.get("ai_acceptance_recommendation"),
                t.get("ai_acceptance_reason"),
            )
        )

    def _read_state(self) -> Optional[dict]:
        """从 SQLite 读取并重建完整状态字典。"""
        conn = self._get_conn()
        try:
            # ── 列 ──
            columns = {}
            for row in conn.execute("SELECT * FROM columns_config ORDER BY ord"):
                columns[row["id"]] = {
                    "id": row["id"],
                    "title": row["title"],
                    "wip_limit": row["wip_limit"],
                    "order": row["ord"],
                    "visible": bool(row["visible"]),
                }
            if not columns:
                return None  # 空数据库，尚未初始化

            # ── 任务 ──
            tasks = {}
            for row in conn.execute("SELECT * FROM tasks"):
                t = dict(row)
                # 布尔字段
                t["is_blocked"] = bool(t["is_blocked"])
                t["is_rii"] = bool(t["is_rii"])
                t["ai_proposed"] = bool(t["ai_proposed"])
                t["parts_available"] = bool(t["parts_available"])
                # JSON 数组字段
                t["checklist"] = json.loads(t.pop("checklist_json", "[]"))
                t["ai_suggestions"] = json.loads(t.pop("ai_suggestions_json", "[]"))
                t["ad_numbers"] = json.loads(t.pop("ad_numbers_json", "[]"))
                t["sb_numbers"] = json.loads(t.pop("sb_numbers_json", "[]"))
                # 清理多余 key
                for json_key in ("checklist_json", "ai_suggestions_json",
                                 "ad_numbers_json", "sb_numbers_json"):
                    t.pop(json_key, None)
                tasks[row["id"]] = t

            # ── 排序 ──
            task_order = {}
            for row in conn.execute(
                "SELECT col_id, task_id FROM task_order ORDER BY position"
            ):
                col_id = row["col_id"]
                if col_id not in task_order:
                    task_order[col_id] = []
                if row["task_id"] in tasks:
                    task_order[col_id].append(row["task_id"])

            # ── 飞机 ──
            aircraft = []
            for row in conn.execute("SELECT * FROM aircraft"):
                aircraft.append({
                    "registration": row["registration"],
                    "model": row["model"],
                    "msn": row["msn"],
                    "status": row["status"],
                    "total_hours": row["total_hours"],
                    "total_cycles": row["total_cycles"],
                    "current_location": row["current_location"],
                    "open_defects": row["open_defects"],
                    "due_tasks_count": row["due_tasks_count"],
                    "overdue_tasks_count": row["overdue_tasks_count"],
                })

            return {
                "columns": columns,
                "tasks": tasks,
                "task_order": task_order,
                "aircraft": aircraft,
            }
        finally:
            conn.close()

    # ── 内部 ──

    def _schedule_save(self):
        """延迟保存（防抖）。"""
        if self._save_timer:
            self._save_timer.cancel()
        self._save_timer = threading.Timer(self._debounce_seconds, self._do_save)
        self._save_timer.daemon = True
        self._save_timer.start()

    def _do_save(self):
        self.save()

    @classmethod
    def reset(cls):
        """重置单例（测试用）。"""
        cls._instance = None


# 全局单例
persistence_service = PersistenceService()
