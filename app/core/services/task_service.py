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
        due_date: Optional[datetime] = None,
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
            due_date=due_date,
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
