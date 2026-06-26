"""任务/工单数据模型."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Priority(str, Enum):
    AOG = "aog"
    CAT_A = "cat_a"
    CAT_B = "cat_b"
    CAT_C = "cat_c"
    CAT_D = "cat_d"


class TaskType(str, Enum):
    TROUBLESHOOT = "troubleshoot"
    INSPECTION = "inspection"
    SERVICING = "servicing"
    REMOVAL_INSTALL = "removal_install"
    TEST = "test"
    REPAIR = "repair"


class TaskStatus(str, Enum):
    BACKLOG = "backlog"
    TRIAGE = "triage"
    SCHEDULED = "scheduled"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    INSPECTION = "inspection"
    PARTS_HOLD = "parts_hold"
    COMPLETED = "completed"
    ARCHIVED = "archived"


@dataclass
class ChecklistItem:
    """检查清单单项。"""
    id: str
    text: str
    completed: bool = False
    completed_by: Optional[str] = None
    completed_at: Optional[datetime] = None

    def toggle(self, user: str):
        self.completed = not self.completed
        if self.completed:
            self.completed_by = user
            self.completed_at = datetime.now()
        else:
            self.completed_by = None
            self.completed_at = None


@dataclass
class StatusChange:
    """状态变更记录。"""
    from_status: TaskStatus
    to_status: TaskStatus
    timestamp: datetime
    changed_by: str
    comment: str = ""


@dataclass
class Task:
    """航空维修任务/工单。

    核心实体，对应看板上的一张卡片。
    """

    id: str
    title: str
    description: str = ""

    # ── 航空核心字段 ──
    aircraft_reg: str = ""          # 飞机注册号 (尾号)，如 "B-5823"
    aircraft_model: str = ""        # 机型，如 "737-800"
    ata_chapter: str = ""           # ATA 章节，如 "32-41-03"
    ata_section: str = ""           # ATA 节号，如 "32"
    ata_page_block: str = ""        # 页面块类型，如 "101" (排故)
    zone: str = ""                  # 维护区域，如 "710"
    fault_code: str = ""            # 标准化故障码

    # ── 分类 ──
    priority: Priority = Priority.CAT_C
    task_type: TaskType = TaskType.TROUBLESHOOT
    status: TaskStatus = TaskStatus.BACKLOG

    # ── 时间 ──
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    due_date: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    estimated_hours: float = 0.0
    actual_hours: float = 0.0

    # ── 人员 ──
    assignee: Optional[str] = None          # 指派技师
    created_by: str = ""                    # 创建者
    inspector: Optional[str] = None         # 检查员 (RII)

    # ── 关联 ──
    parent_task_id: Optional[str] = None
    blocked_by: list[str] = field(default_factory=list)
    sub_tasks: list[str] = field(default_factory=list)
    related_wo_ids: list[str] = field(default_factory=list)

    # ── 合规 ──
    ad_numbers: list[str] = field(default_factory=list)   # 适航指令
    sb_numbers: list[str] = field(default_factory=list)   # 服务通告
    is_rii: bool = False                                   # 必检项目
    mel_item: str = ""                                     # MEL 条目

    # ── 零件 ──
    parts_required: list[str] = field(default_factory=list)
    parts_available: bool = True
    tools_required: list[str] = field(default_factory=list)

    # ── 清单 ──
    checklist: list[ChecklistItem] = field(default_factory=list)

    # ── 状态历史 ──
    status_history: list[StatusChange] = field(default_factory=list)

    # ── AI 元数据 ──
    ai_priority: Optional[Priority] = None
    ai_ata_chapter: Optional[str] = None
    ai_suggestions: list[dict] = field(default_factory=list)
    rag_references: list[dict] = field(default_factory=list)

    def transition_to(self, new_status: TaskStatus, changed_by: str,
                      comment: str = "") -> "Task":
        """创建状态变更后的新 Task（不可变模式）。"""
        self.status_history.append(StatusChange(
            from_status=self.status,
            to_status=new_status,
            timestamp=datetime.now(),
            changed_by=changed_by,
            comment=comment,
        ))
        self.status = new_status
        self.updated_at = datetime.now()
        if new_status == TaskStatus.COMPLETED:
            self.completed_at = datetime.now()
        return self

    def add_checklist_item(self, text: str) -> ChecklistItem:
        """添加检查清单项。"""
        import uuid
        item = ChecklistItem(id=str(uuid.uuid4())[:8], text=text)
        self.checklist.append(item)
        return item

    def checklist_progress(self) -> tuple[int, int]:
        """返回 (已完成, 总数)。"""
        if not self.checklist:
            return 0, 0
        done = sum(1 for item in self.checklist if item.completed)
        return done, len(self.checklist)

    @property
    def is_overdue(self) -> bool:
        """是否已逾期。"""
        if self.due_date and self.status not in (
            TaskStatus.COMPLETED, TaskStatus.ARCHIVED
        ):
            return datetime.now() > self.due_date
        return False

    @property
    def priority_order(self) -> int:
        """优先级排序权重（越小越优先）。"""
        return {
            Priority.AOG: 0,
            Priority.CAT_A: 1,
            Priority.CAT_B: 2,
            Priority.CAT_C: 3,
            Priority.CAT_D: 4,
        }[self.priority]

    def to_dict(self) -> dict:
        """转换为字典（用于序列化）。"""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "aircraft_reg": self.aircraft_reg,
            "aircraft_model": self.aircraft_model,
            "ata_chapter": self.ata_chapter,
            "ata_section": self.ata_section,
            "priority": self.priority.value,
            "task_type": self.task_type.value,
            "status": self.status.value,
            "assignee": self.assignee,
            "estimated_hours": self.estimated_hours,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "created_at": self.created_at.isoformat(),
            "is_rii": self.is_rii,
            "is_overdue": self.is_overdue,
            "checklist_done": self.checklist_progress()[0],
            "checklist_total": self.checklist_progress()[1],
        }
