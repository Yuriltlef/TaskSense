"""命令队列 — 员工窗口 → 主应用 IPC。

员工窗口将操作命令写入 data/pending_commands.json，
主应用轮询该文件并执行命令，执行后更新 board_state.json。
员工窗口通过 mtime 轮询检测 board_state.json 变更并刷新 UI。

命令格式:
    {
        "id": "cmd_<uuid>",
        "action": "accept_task | block_task | submit_task",
        "task_id": "...",
        "employee_id": "ZH001",
        "employee_name": "张工",
        "params": {"reason": "...", "handover_log": "...", "actual_hours": 0},
        "timestamp": "2026-07-07T16:00:00"
    }
"""

import json
import os
import uuid
from datetime import datetime
from typing import Optional

from app.core.services.employee_service import employee_service
from app.core.services.task_service import task_service
from app.core.state import state


def _resolve_path(path: str) -> str:
    if not os.path.isabs(path):
        project_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..")
        )
        path = os.path.join(project_root, path)
    return path


def _read_commands(path: str) -> list[dict]:
    """读取命令队列。"""
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _write_commands(path: str, commands: list[dict]):
    """写入命令队列。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(commands, f, ensure_ascii=False, indent=2)


# ── 员工窗口侧：发送命令 ──


def send_command(
    action: str,
    task_id: str,
    employee_id: str,
    employee_name: str,
    params: dict | None = None,
    queue_path: str = "data/pending_commands.json",
) -> str:
    """将操作命令写入队列文件。返回命令 ID。"""
    path = _resolve_path(queue_path)

    cmd = {
        "id": f"cmd_{uuid.uuid4().hex[:8]}",
        "action": action,
        "task_id": task_id,
        "employee_id": employee_id,
        "employee_name": employee_name,
        "params": params or {},
        "timestamp": datetime.now().isoformat(),
    }

    commands = _read_commands(path)
    commands.append(cmd)
    _write_commands(path, commands)

    return cmd["id"]


# ── 主应用侧：写员工状态 API ──


def write_employee_state(
    board_path: str = "data/board_state.json",
    employee_path: str = "data/employee_state.json",
):
    """将 board_state.json 复制到 employee_state.json（员工读取 API）。"""
    import shutil
    src = _resolve_path(board_path)
    dst = _resolve_path(employee_path)
    if os.path.exists(src):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)


# ── 关闭信号 ──

SHUTDOWN_SIGNAL_PATH = "data/shutdown.signal"


def write_shutdown_signal():
    """写入关闭信号文件，通知所有员工窗口优雅关闭。"""
    path = _resolve_path(SHUTDOWN_SIGNAL_PATH)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("shutdown")


# ── 主应用侧：处理命令 ──


def process_pending_commands(
    queue_path: str = "data/pending_commands.json",
) -> int:
    """处理所有待处理的命令。返回处理的命令数量。"""
    path = _resolve_path(queue_path)
    commands = _read_commands(path)

    if not commands:
        return 0

    processed = 0
    remaining = []

    for cmd in commands:
        try:
            _execute_command(cmd)
            processed += 1
        except Exception as e:
            # 执行失败：保留命令并附加错误信息
            cmd["_error"] = str(e)
            cmd["_retries"] = cmd.get("_retries", 0) + 1
            if cmd["_retries"] <= 3:
                remaining.append(cmd)
            else:
                # 超过重试次数，丢弃
                print(f"[CommandQueue] 命令 {cmd['id']} 失败超过 3 次，已丢弃: {e}")

    # 写回未处理的命令
    _write_commands(path, remaining)

    # 注意：write_employee_state() 由 persistence_service.save() 统一调用，
    # 确保 board_state.json 已更新后再同步到 employee_state.json。
    return processed


def _execute_command(cmd: dict):
    """执行单个命令。抛出异常表示失败。"""
    action = cmd["action"]
    task_id = cmd["task_id"]
    employee_id = cmd.get("employee_id", "")
    employee_name = cmd.get("employee_name", "")
    params = cmd.get("params", {})

    # 校验员工
    if not employee_service.validate(employee_id):
        raise ValueError(f"员工 {employee_id} 不可用")

    # 校验任务存在
    task = state.get_task(task_id)
    if not task:
        raise ValueError(f"任务 {task_id} 不存在")

    if action == "accept_task":
        from app.core.models.task import TaskStatus
        if task.status != TaskStatus.READY:
            raise ValueError(f"任务状态不是「就绪」，无法接单")
        if task.employee_id != employee_id:
            raise ValueError("该任务未指派给您")

        if not task.planned_start:
            task_service.update_task(task_id, planned_start=datetime.now())
        task_service.move_task(task_id, "in_progress", changed_by=employee_name)

    elif action == "block_task":
        from app.core.models.task import TaskStatus
        reason = params.get("reason", "").strip()
        if not reason:
            raise ValueError("阻塞原因不能为空")
        if task.status != TaskStatus.IN_PROGRESS:
            raise ValueError(f"任务状态不是「执行中」，无法阻塞")
        if task.employee_id != employee_id:
            raise ValueError("该任务未指派给您")

        task_service.block_task(task_id, reason=reason, user=employee_name)

    elif action == "submit_task":
        from app.core.models.task import TaskStatus
        if task.status != TaskStatus.IN_PROGRESS:
            raise ValueError(f"任务状态不是「执行中」，无法提交")
        if task.employee_id != employee_id:
            raise ValueError("该任务未指派给您")

        handover_log = params.get("handover_log", "").strip()
        if not handover_log:
            raise ValueError("交接班日志不能为空")

        actual_hours = float(params.get("actual_hours", 0))
        task_service.update_task(
            task_id, shift_handover_log=handover_log,
            actual_hours=actual_hours)
        task_service.move_task(task_id, "inspection", changed_by=employee_name)

    else:
        raise ValueError(f"未知命令类型: {action}")
