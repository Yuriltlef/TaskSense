"""日志数据模型。

记录所有看板操作的审计日志。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class LogType(str, Enum):
    """日志类型。"""
    CREATE_TASK = "create_task"
    DELETE_TASK = "delete_task"
    EDIT_TASK = "edit_task"
    KANBAN_MOVE = "kanban_move"
    SUBMISSION = "submission"           # 提交到验收
    BLOCK = "block"                     # 阻塞
    UNBLOCK = "unblock"                 # 取消阻塞
    REVIEW_APPROVE = "review_approve"   # 审核通过
    REVIEW_REJECT = "review_reject"     # 审核驳回
    REVIEW_AI_SUGGEST = "review_ai"     # AI 审核建议
    SYSTEM_AUTO = "system_auto"         # 系统自动流转


@dataclass
class LogEntry:
    """单条日志记录。"""

    id: str
    timestamp: datetime = field(default_factory=datetime.now)
    log_type: LogType = LogType.SYSTEM_AUTO
    task_id: str = ""
    task_title: str = ""
    user: str = "system"
    description: str = ""
    details: dict = field(default_factory=dict)
    previous_state: Optional[dict] = None
    new_state: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "log_type": self.log_type.value,
            "task_id": self.task_id,
            "task_title": self.task_title,
            "user": self.user,
            "description": self.description,
            "details": self.details,
            "previous_state": self.previous_state,
            "new_state": self.new_state,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LogEntry":
        return cls(
            id=d.get("id", ""),
            timestamp=datetime.fromisoformat(d["timestamp"]) if d.get("timestamp") else datetime.now(),
            log_type=LogType(d.get("log_type", "system_auto")),
            task_id=d.get("task_id", ""),
            task_title=d.get("task_title", ""),
            user=d.get("user", "system"),
            description=d.get("description", ""),
            details=d.get("details", {}),
            previous_state=d.get("previous_state"),
            new_state=d.get("new_state"),
        )
