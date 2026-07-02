"""Agent 写工具 — 创建、更新、分类、排程任务."""

import json
from datetime import datetime

from langchain.tools import tool

from app.core.state import state
from app.core.events import event_bus, AppEvent, EventType
from app.core.services.task_service import task_service
from app.core.validators import TaskValidators, BusinessRuleError


@tool
def create_task(tasks_json: str) -> str:
    """批量创建任务到待处理列。

    Args:
        tasks_json: JSON 字符串，任务对象数组。每个对象可含:
            title(必填), description, aircraft_reg, ata_chapter,
            priority(默认cat_c), task_type(默认troubleshoot),
            zone, estimated_hours, employee_id, employee_name

    Returns:
        创建结果，含各任务 ID 和工卡号
    """
    try:
        tasks_data = json.loads(tasks_json)
    except json.JSONDecodeError:
        return "[Error] 任务数据格式无效，需要 JSON 数组"

    if not isinstance(tasks_data, list):
        tasks_data = [tasks_data]

    created = []
    for td in tasks_data:
        title = td.get("title", "").strip()
        if not title:
            created.append({"error": "标题为空", "data": td})
            continue
        try:
            t = task_service.create_task(
                title=title,
                description=td.get("description", ""),
                aircraft_reg=td.get("aircraft_reg", ""),
                ata_chapter=td.get("ata_chapter", ""),
                priority=td.get("priority", "cat_c"),
                task_type=td.get("task_type", "troubleshoot"),
                assignee=td.get("employee_name") or td.get("assignee"),
                employee_id=td.get("employee_id", ""),
                employee_name=td.get("employee_name", ""),
                estimated_hours=float(td.get("estimated_hours", 0)),
                zone=td.get("zone", ""),
            )
            # AI 创建的任务标记为待确认（幽灵卡片）
            state.update_task(t.id, ai_proposed=True, created_by="ai_agent")

            # 发射幽灵提案事件
            from app.core.events import event_bus
            event_bus.emit(AppEvent(
                type=EventType.AI_PROPOSAL_CREATED,
                data={"task_id": t.id, "title": t.title, "proposal_type": "new_task"},
            ))

            created.append({
                "id": t.id,
                "work_order_id": t.work_order_id,
                "title": t.title,
                "status": "proposed",
                "confirm_needed": True,
            })
        except BusinessRuleError as e:
            created.append({"error": e.message, "data": td})
        except Exception as e:
            created.append({"error": str(e), "data": td})

    return json.dumps(created, ensure_ascii=False, indent=2)


@tool
def update_task(task_id: str, fields_json: str) -> str:
    """更新任务字段。

    Args:
        task_id: 任务 ID
        fields_json: JSON 字符串，要更新的字段键值对。
            可更新: title, description, aircraft_reg, ata_chapter, zone,
            employee_id, employee_name, estimated_hours

    Returns:
        更新结果
    """
    try:
        fields = json.loads(fields_json)
    except json.JSONDecodeError:
        return "[Error] 字段格式无效，需要 JSON 对象"

    task = state.get_task(task_id)
    if not task:
        return f"[Error] 任务 {task_id} 不存在"

    try:
        task_service.update_task(task_id, **fields)
        return json.dumps({
            "task_id": task_id,
            "work_order_id": task.work_order_id,
            "title": task.title,
            "updated_fields": list(fields.keys()),
        }, ensure_ascii=False)
    except Exception as e:
        return f"[Error] 更新失败: {e}"


@tool
def classify_task(task_id: str, priority: str) -> str:
    """为任务设置优先级并移至已分类列。

    Args:
        task_id: 任务 ID
        priority: 优先级 (aog | cat_a | cat_b | cat_c | cat_d)

    Returns:
        分类结果
    """
    valid = {"aog", "cat_a", "cat_b", "cat_c", "cat_d"}
    if priority not in valid:
        return f"[Error] 无效优先级 '{priority}'，可选: {', '.join(sorted(valid))}"

    task = state.get_task(task_id)
    if not task:
        return f"[Error] 任务 {task_id} 不存在"

    if task.status.value != "backlog":
        return f"[Error] 任务 {task_id} 当前状态为 '{task.status.value}'，只能分类待处理任务"

    try:
        task_service.move_task(task_id, "triage", changed_by="ai_agent")
        task_service.set_priority(task_id, priority)
        return json.dumps({
            "task_id": task_id,
            "title": task.title,
            "priority": priority,
            "status": "triage",
        }, ensure_ascii=False)
    except Exception as e:
        return f"[Error] 分类失败: {e}"


@tool
def schedule_task(task_id: str, planned_start: str = "",
                  planned_end: str = "", employee_id: str = "",
                  employee_name: str = "", estimated_hours: float = 0.0) -> str:
    """为已分类任务排程，设置计划时间和负责人，移至已排程列。

    Args:
        task_id: 任务 ID
        planned_start: 计划开始时间 (YYYY-MM-DD HH:MM)
        planned_end: 计划完成时间 (YYYY-MM-DD HH:MM)
        employee_id: 员工 ID
        employee_name: 员工姓名
        estimated_hours: 计划工时（小时）

    Returns:
        排程结果
    """
    task = state.get_task(task_id)
    if not task:
        return f"[Error] 任务 {task_id} 不存在"

    if task.status.value != "triage":
        return f"[Error] 任务 {task_id} 当前状态为 '{task.status.value}'，只能排程已分类任务"

    updates = {}
    if planned_start:
        try:
            updates["planned_start"] = datetime.strptime(planned_start, "%Y-%m-%d %H:%M")
        except ValueError:
            return f"[Error] 计划开始时间格式无效: '{planned_start}'，需要 YYYY-MM-DD HH:MM"
    if planned_end:
        try:
            updates["planned_end"] = datetime.strptime(planned_end, "%Y-%m-%d %H:%M")
        except ValueError:
            return f"[Error] 计划完成时间格式无效: '{planned_end}'，需要 YYYY-MM-DD HH:MM"
    if employee_id:
        updates["employee_id"] = employee_id
    if employee_name:
        updates["employee_name"] = employee_name
        updates["assignee"] = employee_name
    if estimated_hours > 0:
        updates["estimated_hours"] = estimated_hours

    if updates:
        task_service.update_task(task_id, **updates)

    try:
        task_service.move_task(task_id, "scheduled", changed_by="ai_agent")
        return json.dumps({
            "task_id": task_id,
            "title": task.title,
            "status": "scheduled",
            "updates": updates,
        }, ensure_ascii=False, default=str)
    except Exception as e:
        return f"[Error] 排程失败: {e}"
