"""任务/工单数据模型."""

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

# 全局面工卡号计数器
_wo_counter: int = 0
_wo_lock = threading.Lock()


def _generate_work_order_id() -> str:
    """生成工卡号：WO-YYYYMMDD-NNN。"""
    global _wo_counter
    with _wo_lock:
        _wo_counter += 1
        return f"WO-{datetime.now().strftime('%Y%m%d')}-{_wo_counter:03d}"


def _dt_checklist(v: Optional[str]) -> Optional[datetime]:
    """安全解析 checklist 完成时间。"""
    if v is None:
        return None
    try:
        return datetime.fromisoformat(v)
    except (ValueError, TypeError):
        return None


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
    work_order_id: str = ""             # 工卡号，自动生成 WO-YYYYMMDD-NNN

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
    planned_start: Optional[datetime] = None   # 计划开始时间
    planned_end: Optional[datetime] = None     # 计划完成时间
    completed_at: Optional[datetime] = None
    estimated_hours: float = 0.0
    actual_hours: float = 0.0

    # ── 人员 ──
    assignee: Optional[str] = None          # 指派技师（兼容旧代码）
    employee_id: str = ""                   # 员工 ID，如 ZH001
    employee_name: str = ""                 # 员工姓名，如 张工
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

    # ── 阻塞 / 交接 ──
    is_blocked: bool = False                   # 是否阻塞
    block_reason: str = ""                     # 阻塞原因
    shift_handover_log: str = ""               # 交接班日志

    # ── AI 元数据 ──
    ai_proposed: bool = False                  # AI 建议的任务（需用户确认）
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

    @property
    def remaining_time(self) -> Optional[float]:
        """剩余时间（秒），用于倒计时。仅就绪/执行中状态有效。"""
        if self.planned_end is None:
            return None
        if self.status not in (TaskStatus.READY, TaskStatus.IN_PROGRESS):
            return None
        return (self.planned_end - datetime.now()).total_seconds()

    @property
    def is_countdown_overdue(self) -> bool:
        """倒计时是否已逾期（已超过计划完成时间）。"""
        remaining = self.remaining_time
        return remaining is not None and remaining < 0

    @classmethod
    def from_dict(cls, d: dict) -> "Task":
        """从字典反序列化 Task。"""
        priority = d.get("priority", "cat_c")
        if isinstance(priority, str):
            priority = Priority(priority)
        task_type = d.get("task_type", "troubleshoot")
        if isinstance(task_type, str):
            task_type = TaskType(task_type)
        status = d.get("status", "backlog")
        if isinstance(status, str):
            status = TaskStatus(status)

        def _dt(key):
            v = d.get(key)
            return datetime.fromisoformat(v) if v else None

        task = cls(
            id=d.get("id", ""),
            work_order_id=d.get("work_order_id", ""),
            title=d.get("title", ""),
            description=d.get("description", ""),
            aircraft_reg=d.get("aircraft_reg", ""),
            aircraft_model=d.get("aircraft_model", ""),
            ata_chapter=d.get("ata_chapter", ""),
            ata_section=d.get("ata_section", ""),
            ata_page_block=d.get("ata_page_block", ""),
            zone=d.get("zone", ""),
            fault_code=d.get("fault_code", ""),
            priority=priority,
            task_type=task_type,
            status=status,
            due_date=_dt("due_date"),
            planned_start=_dt("planned_start"),
            planned_end=_dt("planned_end"),
            completed_at=_dt("completed_at"),
            created_at=_dt("created_at") or datetime.now(),
            updated_at=_dt("updated_at") or datetime.now(),
            estimated_hours=d.get("estimated_hours", 0.0),
            actual_hours=d.get("actual_hours", 0.0),
            assignee=d.get("assignee"),
            employee_id=d.get("employee_id", ""),
            employee_name=d.get("employee_name", ""),
            created_by=d.get("created_by", ""),
            inspector=d.get("inspector"),
            is_blocked=d.get("is_blocked", False),
            block_reason=d.get("block_reason", ""),
            shift_handover_log=d.get("shift_handover_log", ""),
            parent_task_id=d.get("parent_task_id"),
            blocked_by=d.get("blocked_by", []),
            sub_tasks=d.get("sub_tasks", []),
            related_wo_ids=d.get("related_wo_ids", []),
            ad_numbers=d.get("ad_numbers", []),
            sb_numbers=d.get("sb_numbers", []),
            is_rii=d.get("is_rii", False),
            mel_item=d.get("mel_item", ""),
            parts_required=d.get("parts_required", []),
            parts_available=d.get("parts_available", True),
            tools_required=d.get("tools_required", []),
            ai_proposed=d.get("ai_proposed", False),
            ai_priority=Priority(ap) if (ap := d.get("ai_priority")) else None,
            ai_ata_chapter=d.get("ai_ata_chapter"),
            ai_suggestions=d.get("ai_suggestions", []),
            rag_references=d.get("rag_references", []),
        )
        # 恢复 checklist
        for ci in d.get("checklist", []):
            item = ChecklistItem(
                id=ci.get("id", ""),
                text=ci.get("text", ""),
                completed=ci.get("completed", False),
                completed_by=ci.get("completed_by"),
                completed_at=_dt_checklist(ci.get("completed_at")),
            )
            task.checklist.append(item)
        # 恢复 status_history
        for sh in d.get("status_history", []):
            sc = StatusChange(
                from_status=TaskStatus(sh["from_status"]),
                to_status=TaskStatus(sh["to_status"]),
                timestamp=datetime.fromisoformat(sh["timestamp"]),
                changed_by=sh.get("changed_by", ""),
                comment=sh.get("comment", ""),
            )
            task.status_history.append(sc)
        return task

    def to_dict(self) -> dict:
        """转换为字典（用于序列化）。"""
        return {
            "id": self.id,
            "work_order_id": self.work_order_id,
            "title": self.title,
            "description": self.description,
            "aircraft_reg": self.aircraft_reg,
            "aircraft_model": self.aircraft_model,
            "ata_chapter": self.ata_chapter,
            "ata_section": self.ata_section,
            "ata_page_block": self.ata_page_block,
            "zone": self.zone,
            "fault_code": self.fault_code,
            "priority": self.priority.value,
            "task_type": self.task_type.value,
            "status": self.status.value,
            "assignee": self.assignee,
            "employee_id": self.employee_id,
            "employee_name": self.employee_name,
            "created_by": self.created_by,
            "inspector": self.inspector,
            "estimated_hours": self.estimated_hours,
            "actual_hours": self.actual_hours,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "planned_start": self.planned_start.isoformat() if self.planned_start else None,
            "planned_end": self.planned_end.isoformat() if self.planned_end else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "is_rii": self.is_rii,
            "is_blocked": self.is_blocked,
            "block_reason": self.block_reason,
            "shift_handover_log": self.shift_handover_log,
            "is_overdue": self.is_overdue,
            "is_countdown_overdue": self.is_countdown_overdue,
            "checklist_done": self.checklist_progress()[0],
            "checklist_total": self.checklist_progress()[1],
            "parent_task_id": self.parent_task_id,
            "blocked_by": self.blocked_by,
            "sub_tasks": self.sub_tasks,
            "related_wo_ids": self.related_wo_ids,
            "ad_numbers": self.ad_numbers,
            "sb_numbers": self.sb_numbers,
            "mel_item": self.mel_item,
            "parts_required": self.parts_required,
            "parts_available": self.parts_available,
            "tools_required": self.tools_required,
            "checklist": [
                {
                    "id": ci.id, "text": ci.text,
                    "completed": ci.completed,
                    "completed_by": ci.completed_by,
                    "completed_at": ci.completed_at.isoformat() if ci.completed_at else None,
                }
                for ci in self.checklist
            ],
            "status_history": [
                {
                    "from_status": sh.from_status.value,
                    "to_status": sh.to_status.value,
                    "timestamp": sh.timestamp.isoformat(),
                    "changed_by": sh.changed_by,
                    "comment": sh.comment,
                }
                for sh in self.status_history
            ],
            "ai_proposed": self.ai_proposed,
            "ai_priority": self.ai_priority.value if self.ai_priority else None,
            "ai_ata_chapter": self.ai_ata_chapter,
            "ai_suggestions": self.ai_suggestions,
            "rag_references": self.rag_references,
        }
