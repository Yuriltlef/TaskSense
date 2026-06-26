"""飞机数据模型."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class AircraftStatus(str, Enum):
    OPERATIONAL = "operational"
    IN_MAINTENANCE = "in_maintenance"
    AOG = "aog"
    STORED = "stored"


@dataclass
class Aircraft:
    """飞机/航空器。

    以注册号 (registration) 为主键。
    """

    registration: str               # 注册号/尾号，如 "B-5823"
    model: str = ""                 # 机型，如 "737-800"
    msn: str = ""                   # 制造商序列号 (Manufacturer Serial Number)
    status: AircraftStatus = AircraftStatus.OPERATIONAL

    # ── 使用参数 ──
    total_hours: float = 0.0        # 总飞行小时 (TAH)
    total_cycles: int = 0           # 总循环数 (TAC)
    hours_since_a_check: float = 0.0
    hours_since_c_check: float = 0.0
    cycles_since_a_check: int = 0

    # ── 维修记录 ──
    last_a_check: Optional[datetime] = None
    last_c_check: Optional[datetime] = None
    last_d_check: Optional[datetime] = None

    # ── 位置 ──
    current_location: str = ""      # 当前位置（机库/停机位）
    current_zone: str = ""          # 当前区域

    # ── 状态 ──
    mel_items: list[str] = field(default_factory=list)     # 当前 MEL 延期项
    open_defects: int = 0                                   # 未关闭故障数
    due_tasks_count: int = 0                                # 待处理任务数
    overdue_tasks_count: int = 0                            # 逾期任务数

    @property
    def display_name(self) -> str:
        """显示名称。"""
        if self.model:
            return f"{self.registration} · {self.model}"
        return self.registration

    @property
    def status_display(self) -> str:
        """状态中文显示。"""
        return {
            AircraftStatus.OPERATIONAL: "运行中",
            AircraftStatus.IN_MAINTENANCE: "维修中",
            AircraftStatus.AOG: "AOG停飞",
            AircraftStatus.STORED: "封存",
        }[self.status]

    def to_dict(self) -> dict:
        return {
            "registration": self.registration,
            "model": self.model,
            "status": self.status.value,
            "total_hours": self.total_hours,
            "total_cycles": self.total_cycles,
            "current_location": self.current_location,
            "open_defects": self.open_defects,
            "due_tasks_count": self.due_tasks_count,
            "overdue_tasks_count": self.overdue_tasks_count,
        }
