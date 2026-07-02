"""任务服务 — 任务生命周期管理."""

from datetime import datetime
from typing import Optional

from app.core.models.task import Priority, Task, TaskStatus, TaskType
from app.core.state import state
from app.core.validators import BusinessRuleError, TaskValidators


class TaskService:
    """任务业务服务。

    封装任务创建、移动、更新的业务逻辑。
    不依赖 UI，不依赖 Agent。
    """

    def __init__(self):
        self.state = state

    def create_task(
        self,
        title: str,
        description: str = "",
        aircraft_reg: str = "",
        aircraft_model: str = "",
        ata_chapter: str = "",
        priority: str = "cat_c",
        task_type: str = "troubleshoot",
        assignee: Optional[str] = None,
        employee_id: str = "",
        employee_name: str = "",
        due_date: Optional[datetime] = None,
        planned_start: Optional[datetime] = None,
        planned_end: Optional[datetime] = None,
        estimated_hours: float = 0.0,
        zone: str = "",
        fault_code: str = "",
        created_by: str = "user",
    ) -> Task:
        """创建新任务。

        Raises:
            BusinessRuleError: 数据校验失败
        """
        # 校验
        TaskValidators.validate_create(title, aircraft_reg)
        if aircraft_reg:
            TaskValidators.validate_aircraft_reg(aircraft_reg)
        if ata_chapter:
            TaskValidators.validate_ata_chapter(ata_chapter)
        if employee_id:
            TaskValidators.validate_employee(employee_id)
        TaskValidators.validate_planned_time(planned_start, planned_end)
        TaskValidators.validate_hours(estimated_hours)

        # 提取 ATA 章节号
        ata_section = ata_chapter.split("-")[0] if ata_chapter else ""

        task = self.state.create_task(
            title=title.strip(),
            description=description,
            aircraft_reg=aircraft_reg.upper(),
            aircraft_model=aircraft_model,
            ata_chapter=ata_chapter,
            ata_section=ata_section,
            priority=Priority(priority),
            task_type=TaskType(task_type),
            assignee=assignee,
            employee_id=employee_id,
            employee_name=employee_name,
            due_date=due_date,
            planned_start=planned_start,
            planned_end=planned_end,
            estimated_hours=estimated_hours,
            zone=zone,
            fault_code=fault_code,
            created_by=created_by,
        )
        return task

    def move_task(
        self,
        task_id: str,
        to_column: str,
        index: int = -1,
        changed_by: str = "user",
    ) -> Optional[Task]:
        """移动任务到目标列。

        Raises:
            BusinessRuleError: 状态转换不合法
        """
        task = self.state.get_task(task_id)
        if not task:
            raise BusinessRuleError(f"任务 '{task_id}' 不存在", "TASK_NOT_FOUND")

        # 同列重排序不改变状态，跳过状态转换校验
        if task.status.value != to_column:
            columns = self.state.get_columns()
            TaskValidators.validate_transition(task, to_column, columns)

        return self.state.move_task(task_id, to_column, index, changed_by)

    def update_task(self, task_id: str, **changes) -> Optional[Task]:
        """更新任务字段。"""
        return self.state.update_task(task_id, **changes)

    def delete_task(self, task_id: str) -> bool:
        """删除任务。"""
        return self.state.delete_task(task_id)

    def assign_task(self, task_id: str, assignee: str) -> Optional[Task]:
        """分配任务给技师。"""
        return self.state.update_task(task_id, assignee=assignee)

    def set_priority(self, task_id: str, priority: str) -> Optional[Task]:
        """设置任务优先级。"""
        task = self.state.get_task(task_id)
        if not task:
            return None
        new_priority = Priority(priority)
        return self.state.update_task(task_id, priority=new_priority)

    # ── 阻塞 / 取消阻塞 ──

    def block_task(self, task_id: str, reason: str, user: str = "user") -> Optional[Task]:
        """阻塞任务，移至 parts_hold 列。

        仅 ready 或 in_progress 状态的任务可阻塞。
        """
        task = self.state.get_task(task_id)
        if not task:
            raise BusinessRuleError("任务不存在", "TASK_NOT_FOUND")

        if task.status not in (TaskStatus.READY, TaskStatus.IN_PROGRESS):
            raise BusinessRuleError(
                f"只有就绪或执行中的任务可以阻塞，当前状态: {task.status.value}",
                "BLOCK_INVALID_STATUS",
            )

        if not reason or not reason.strip():
            raise BusinessRuleError("阻塞原因不能为空", "BLOCK_REASON_REQUIRED")

        # 更新阻塞字段
        self.state.update_task(
            task_id,
            is_blocked=True,
            block_reason=reason.strip(),
        )

        # 记录日志
        from app.core.models.log_entry import LogType
        from app.core.services.log_service import log_service
        log_service.log(
            log_type=LogType.BLOCK,
            task_id=task_id,
            task_title=task.title,
            user=user,
            description=f"阻塞任务: {reason}",
            details={"reason": reason, "from_status": task.status.value},
        )

        # 移动到 parts_hold
        return self.move_task(task_id, "parts_hold", changed_by=user)

    def unblock_task(self, task_id: str, user: str = "user") -> Optional[Task]:
        """取消阻塞，将任务移回 ready 列。"""
        task = self.state.get_task(task_id)
        if not task:
            raise BusinessRuleError("任务不存在", "TASK_NOT_FOUND")

        if not task.is_blocked:
            raise BusinessRuleError("任务未被阻塞", "NOT_BLOCKED")

        # 更新阻塞字段
        self.state.update_task(
            task_id,
            is_blocked=False,
            block_reason="",
        )

        # 记录日志
        from app.core.models.log_entry import LogType
        from app.core.services.log_service import log_service
        log_service.log(
            log_type=LogType.UNBLOCK,
            task_id=task_id,
            task_title=task.title,
            user=user,
            description="取消阻塞",
        )

        # 移回 ready
        return self.move_task(task_id, "ready", changed_by=user)

    def toggle_checklist_item(self, task_id: str, item_id: str,
                              user: str) -> Optional[Task]:
        """切换检查清单项状态。"""
        task = self.state.get_task(task_id)
        if not task:
            return None
        for item in task.checklist:
            if item.id == item_id:
                item.toggle(user)
                self.state.update_task(task_id)  # 触发通知
                return task
        return None


# 全局实例
task_service = TaskService()
