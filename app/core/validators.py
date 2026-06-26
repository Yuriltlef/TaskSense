"""业务规则校验."""

from typing import Optional

from app.config.constants import ALLOWED_TRANSITIONS
from app.core.models.task import Task, TaskStatus
from app.core.models.kanban import ColumnConfig


class BusinessRuleError(Exception):
    """业务规则违反异常。"""

    def __init__(self, message: str, code: str = ""):
        super().__init__(message)
        self.message = message
        self.code = code


class TaskValidators:
    """任务操作校验器。"""

    @staticmethod
    def validate_transition(task: Task, to_column_id: str,
                            columns: list[ColumnConfig]) -> None:
        """校验任务是否可以移动到目标列。

        Raises:
            BusinessRuleError: 如果转换不被允许
        """
        # 查找目标列对应的状态
        target_status = None
        for col in columns:
            if col.id == to_column_id:
                target_status = TaskStatus(col.id)
                break

        if target_status is None:
            raise BusinessRuleError(
                f"目标列 '{to_column_id}' 不存在", "INVALID_COLUMN"
            )

        # 检查是否允许的状态转换
        allowed = ALLOWED_TRANSITIONS.get(task.status.value, [])
        if target_status.value not in allowed:
            raise BusinessRuleError(
                f"不允许从 '{task.status.value}' 移动到 '{target_status.value}'",
                "INVALID_TRANSITION",
            )

    @staticmethod
    def validate_create(title: str, aircraft_reg: str = "") -> None:
        """校验任务创建数据。

        Raises:
            BusinessRuleError: 如果数据不合法
        """
        if not title or not title.strip():
            raise BusinessRuleError("任务标题不能为空", "TITLE_REQUIRED")

        if len(title) > 200:
            raise BusinessRuleError("任务标题不能超过200个字符", "TITLE_TOO_LONG")

    @staticmethod
    def validate_wip(column: ColumnConfig) -> Optional[str]:
        """检查 WIP 限制。返回警告信息或 None。"""
        if column.wip_limit and column.task_count >= column.wip_limit:
            return f"'{column.title}' 列已达 WIP 限制 ({column.wip_limit})"
        return None
