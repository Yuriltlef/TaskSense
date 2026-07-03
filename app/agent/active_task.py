# -*- coding: utf-8 -*-
"""任务锁注册表 — 追踪当前活跃的 AI 工具任务，防止 Agent 偏离。"""

import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class ActiveTask:
    """当前活跃的 AI 工具任务。"""
    session_id: str
    label: str          # 显示名，如 "自动分类"
    phase: str          # "gathering_requirements" | "executing" | "completed"
    started_at: datetime = field(default_factory=datetime.now)
    description: str = ""


class ActiveTaskRegistry:
    """线程安全的活跃任务注册表。

    用法：
        from app.agent.active_task import active_task_registry

        # 任务开始
        active_task_registry.set_active("classify", "自动分类", "executing", "5 tasks")

        # Agent 消息注入（在 orchestrator.ask() 中自动调用）
        msg = active_task_registry.inject_context(question, session_id)

        # 任务结束
        active_task_registry.clear()
    """

    def __init__(self):
        self._active: Optional[ActiveTask] = None
        self._lock = threading.Lock()

    # ── 状态读写 ──

    def set_active(self, session_id: str, label: str, phase: str = "executing",
                   description: str = ""):
        with self._lock:
            self._active = ActiveTask(
                session_id=session_id, label=label,
                phase=phase, description=description,
            )

    def get_active(self) -> Optional[ActiveTask]:
        with self._lock:
            return self._active

    def clear(self):
        with self._lock:
            self._active = None

    def update_phase(self, phase: str):
        with self._lock:
            if self._active:
                self._active.phase = phase

    def is_active(self) -> bool:
        with self._lock:
            return self._active is not None

    # ── 消息注入 ──

    @staticmethod
    def _load_guard_text() -> str:
        """加载 task_guard.md（含文件缓存避免重复 IO）。"""
        if not hasattr(ActiveTaskRegistry, '_guard_cache'):
            path = Path(__file__).parent / "prompts" / "task_guard.md"
            if path.exists():
                ActiveTaskRegistry._guard_cache = path.read_text(encoding="utf-8")
            else:
                ActiveTaskRegistry._guard_cache = ""
        return ActiveTaskRegistry._guard_cache

    def inject_context(self, question: str, session_id: str) -> str:
        """若存在活跃任务且 session 不匹配，前缀注入守卫上下文。
        否则原样返回。
        """
        active = self.get_active()
        if not active:
            return question

        # 同 session 已含任务上下文，不重复注入
        if session_id == active.session_id:
            return question

        guard = self._load_guard_text()
        if not guard:
            return question

        # 填充守卫模板
        guard_filled = guard.replace("{task_label}", active.label)
        guard_filled = guard_filled.replace("{task_description}", active.description)
        guard_filled = guard_filled.replace("{task_phase}", active.phase)

        return f"""{guard_filled}

---

用户消息: {question}"""


# 全局实例
active_task_registry = ActiveTaskRegistry()
