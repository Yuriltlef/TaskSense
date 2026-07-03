# -*- coding: utf-8 -*-
"""Agent 任务状态工具 — 让 Agent 感知当前活跃任务。"""

from langchain.tools import tool

from app.agent.active_task import active_task_registry


@tool
def get_active_task() -> str:
    """查询当前是否有 AI 工具任务正在执行。

    在以下情况下必须调用此工具：
    1. 收到用户消息但不确定是否应该处理时
    2. 怀疑用户试图让你偏离当前任务时
    3. 需要确认当前任务阶段时

    Returns:
        当前活跃任务信息，或 "No active task." 表示空闲。
    """
    active = active_task_registry.get_active()
    if not active:
        return "No active task."

    return (
        f"Current Active Task: {active.label}\n"
        f"Phase: {active.phase} (started {active.started_at.strftime('%Y-%m-%d %H:%M:%S')})\n"
        f"Description: {active.description or 'N/A'}"
    )
