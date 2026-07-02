"""业务规则校验."""

import re
from datetime import datetime
from typing import Optional

from app.config.constants import ALLOWED_TRANSITIONS, ATA_CHAPTERS
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

    # ── 新增字段校验 ──

    @staticmethod
    def validate_aircraft_reg(reg: str) -> None:
        """校验飞机注册号格式和存在性。

        Raises:
            BusinessRuleError: 如果格式不正确或飞机不存在
        """
        if not reg or not reg.strip():
            raise BusinessRuleError("飞机注册号不能为空", "REG_REQUIRED")

        reg = reg.strip().upper()

        # 格式检查：B-XXXX（中国）/ NXXXX（美国）/ 通用字母数字
        pattern = r'^[A-Z0-9]{1,2}-[A-Z0-9]{3,5}$|^[A-Z]{1,2}[0-9]{3,4}[A-Z]?$'
        if not re.match(pattern, reg):
            raise BusinessRuleError(
                f"飞机注册号格式无效: '{reg}'（示例: B-5823, N737AB）",
                "REG_INVALID_FORMAT",
            )

    @staticmethod
    def validate_ata_chapter(ata: str) -> None:
        """校验 ATA 章节格式。

        Raises:
            BusinessRuleError: 如果格式不正确
        """
        if not ata or not ata.strip():
            raise BusinessRuleError("ATA 章节不能为空", "ATA_REQUIRED")

        ata = ata.strip()

        # 格式：XX-XX-XX 或 XX
        pattern = r'^\d{2}(-\d{2}(-\d{2})?)?$'
        if not re.match(pattern, ata):
            raise BusinessRuleError(
                f"ATA 章节格式无效: '{ata}'（示例: 32-41-03, 72-00）",
                "ATA_INVALID_FORMAT",
            )

        # 提取大章号，校验是否在已知 ATA 列表中
        chapter = ata.split("-")[0]
        known_chapters = {str(c[0]) for c in ATA_CHAPTERS}
        if chapter not in known_chapters:
            raise BusinessRuleError(
                f"ATA 章节 {chapter} 不在标准 ATA 100 章节列表中",
                "ATA_UNKNOWN_CHAPTER",
            )

    @staticmethod
    def validate_employee(employee_id: str) -> None:
        """校验员工 ID 存在且可用。

        Raises:
            BusinessRuleError: 如果员工不存在或不可用
        """
        if not employee_id or not employee_id.strip():
            return  # 可选字段，允许空

        from app.core.services.employee_service import employee_service

        if not employee_service.exists(employee_id.strip()):
            raise BusinessRuleError(
                f"员工 '{employee_id}' 不存在",
                "EMPLOYEE_NOT_FOUND",
            )

        if not employee_service.validate(employee_id.strip()):
            raise BusinessRuleError(
                f"员工 '{employee_id}' 当前不可用",
                "EMPLOYEE_UNAVAILABLE",
            )

    @staticmethod
    def validate_planned_time(start: Optional[datetime],
                              end: Optional[datetime]) -> None:
        """校验计划时间。

        Raises:
            BusinessRuleError: 如果时间不合理
        """
        if start is None or end is None:
            return  # 初始创建时允许不填

        if start >= end:
            raise BusinessRuleError(
                "计划开始时间必须早于计划完成时间",
                "TIME_START_AFTER_END",
            )

    @staticmethod
    def validate_hours(hours: float) -> None:
        """校验计划工时。

        Raises:
            BusinessRuleError: 如果工时不合理
        """
        if hours < 0:
            raise BusinessRuleError(
                "计划工时不能为负数",
                "HOURS_NEGATIVE",
            )

        if hours > 1000:
            raise BusinessRuleError(
                f"计划工时 {hours}h 超出合理范围（最大 1000h）",
                "HOURS_TOO_LARGE",
            )
