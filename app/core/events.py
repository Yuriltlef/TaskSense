"""事件总线 — 跨层通信."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Any


class EventType(str, Enum):
    TASK_CREATED = "task_created"
    TASK_MOVED = "task_moved"
    TASK_UPDATED = "task_updated"
    TASK_DELETED = "task_deleted"
    TASK_OVERDUE = "task_overdue"
    BOARD_CHANGED = "board_changed"
    WIP_EXCEEDED = "wip_exceeded"
    ANOMALY_DETECTED = "anomaly_detected"
    COMPLIANCE_ALERT = "compliance_alert"
    REPORT_GENERATED = "report_generated"
    FILTER_CHANGED = "filter_changed"


@dataclass
class AppEvent:
    """应用事件。"""
    type: EventType
    data: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


class EventBus:
    """发布/订阅事件总线。

    用于跨层解耦通信：
    - Agent 检测到异常 → emit(ANOMALY_DETECTED) → UI 收到通知
    - 任务状态变更 → emit(TASK_MOVED) → Anomaly Agent 检查模式
    """

    def __init__(self):
        self._handlers: dict[EventType, list[Callable]] = {}

    def on(self, event_type: EventType, handler: Callable[[AppEvent], Any]):
        """注册事件处理器。"""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def off(self, event_type: EventType, handler: Callable):
        """移除事件处理器。"""
        if event_type in self._handlers:
            self._handlers[event_type] = [
                h for h in self._handlers[event_type] if h is not handler
            ]

    def emit(self, event: AppEvent):
        """发布事件。"""
        handlers = self._handlers.get(event.type, [])
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                # 事件处理器异常不应中断其他处理器
                pass

    def clear(self):
        """清除所有处理器。"""
        self._handlers.clear()


# 全局事件总线实例
event_bus = EventBus()
