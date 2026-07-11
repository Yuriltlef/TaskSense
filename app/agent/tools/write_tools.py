"""Agent 写工具 — 创建、更新、分类、排程任务."""

import json
from datetime import datetime

from langchain.tools import tool

from app.core.events import event_bus, AppEvent, EventType
from app.core.services.task_service import task_service
from app.core.state import state
from app.core.validators import BusinessRuleError


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


# update_task 允许更新的字段白名单（防止 LLM 直接改写 status/priority 等关键字段）
_UPDATE_ALLOWED = {
    "title", "description", "aircraft_reg", "aircraft_model",
    "ata_chapter", "zone", "fault_code",
    "employee_id", "employee_name", "assignee", "inspector",
    "estimated_hours", "actual_hours", "due_date",
    "planned_start", "planned_end",
    "shift_handover_log", "is_rii",
    "ad_numbers", "sb_numbers", "mel_item",
    "parts_required", "parts_available", "tools_required",
}


@tool
def update_task(task_id: str, fields_json: str) -> str:
    """更新任务字段（仅安全白名单内的字段可更新）。

    Args:
        task_id: 任务 ID
        fields_json: JSON 对象字符串，可更新字段:
            title, description, aircraft_reg, aircraft_model,
            ata_chapter, zone, fault_code,
            employee_id, employee_name, assignee, inspector,
            estimated_hours, actual_hours, due_date,
            planned_start, planned_end,
            shift_handover_log, is_rii,
            ad_numbers, sb_numbers, mel_item,
            parts_required, parts_available, tools_required

    Returns:
        更新结果（被拒绝的字段会列出）
    """
    try:
        fields = json.loads(fields_json)
    except json.JSONDecodeError:
        return "[Error] 字段格式无效，需要 JSON 对象"

    task = state.get_task(task_id)
    if not task:
        return f"[Error] 任务 {task_id} 不存在"

    # 白名单过滤：阻止 LLM 修改 status/priority/ai_* 等关键状态字段
    allowed_fields = {k: v for k, v in fields.items() if k in _UPDATE_ALLOWED}
    rejected = [k for k in fields if k not in _UPDATE_ALLOWED]
    if rejected:
        from app.core.logging import log
        log.warn("safety.update_task", task_id=task_id, rejected=str(rejected))

    if not allowed_fields:
        return (f"[Error] 所有请求字段被安全策略拒绝: {rejected}。"
                f"允许的字段: {sorted(_UPDATE_ALLOWED)}")

    # 日期时间字段类型转换：LLM 传字符串 → datetime 对象
    _DATETIME_FIELDS = {"due_date", "planned_start", "planned_end", "completed_at"}
    for k in _DATETIME_FIELDS:
        if k in allowed_fields and isinstance(allowed_fields[k], str):
            try:
                allowed_fields[k] = datetime.fromisoformat(allowed_fields[k])
            except (ValueError, TypeError):
                pass  # 保持原值，后续保存/渲染时自然暴露问题

    try:
        task_service.update_task(task_id, **allowed_fields)
        result = {
            "task_id": task_id,
            "work_order_id": task.work_order_id,
            "title": task.title,
            "updated_fields": list(allowed_fields.keys()),
        }
        if rejected:
            result["rejected_fields"] = rejected
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return f"[Error] 更新失败: {e}"


@tool
def classify_task(task_id: str, priority: str) -> str:
    """为任务设置优先级并标记为待确认分类建议。

    Args:
        task_id: 任务 ID
        priority: 优先级 (aog | cat_a | cat_b | cat_c | cat_d)

    Returns:
        分类结果（需用户确认后生效）
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
        from app.core.models.task import Priority
        state.update_task(task_id, ai_proposed=True,
                          ai_priority=Priority(priority),
                          created_by="ai_agent")
        event_bus.emit(AppEvent(
            type=EventType.AI_PROPOSAL_CREATED,
            data={"task_id": task_id, "title": task.title,
                  "proposal_type": "classify", "priority": priority},
        ))
        return json.dumps({
            "task_id": task_id,
            "title": task.title,
            "proposed_priority": priority,
            "action": "proposed",
            "confirm_needed": True,
        }, ensure_ascii=False)
    except Exception as e:
        return f"[Error] 分类失败: {e}"


@tool
def schedule_task(task_id: str, planned_start: str = "",
                  planned_end: str = "", employee_id: str = "",
                  employee_name: str = "", estimated_hours: float = 0.0) -> str:
    """为已分类任务排程，标记为待确认排程建议。

    Args:
        task_id: 任务 ID
        planned_start: 计划开始时间 (YYYY-MM-DD HH:MM)
        planned_end: 计划完成时间 (YYYY-MM-DD HH:MM)
        employee_id: 员工 ID
        employee_name: 员工姓名
        estimated_hours: 计划工时（小时）

    Returns:
        排程结果（需用户确认后生效）
    """
    task = state.get_task(task_id)
    if not task:
        return f"[Error] 任务 {task_id} 不存在"

    if task.status.value != "triage":
        return f"[Error] 任务 {task_id} 当前状态为 '{task.status.value}'，只能排程已分类任务"

    proposal = {"proposal_type": "schedule"}
    if planned_start:
        try:
            proposal["planned_start"] = datetime.strptime(planned_start, "%Y-%m-%d %H:%M").strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return f"[Error] 计划开始时间格式无效: '{planned_start}'，需要 YYYY-MM-DD HH:MM"
    if planned_end:
        try:
            proposal["planned_end"] = datetime.strptime(planned_end, "%Y-%m-%d %H:%M").strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return f"[Error] 计划完成时间格式无效: '{planned_end}'，需要 YYYY-MM-DD HH:MM"
    if employee_id:
        proposal["employee_id"] = employee_id
    if employee_name:
        proposal["employee_name"] = employee_name
    if estimated_hours > 0:
        proposal["estimated_hours"] = estimated_hours

    try:
        ai_suggestions = list(task.ai_suggestions or [])
        ai_suggestions[:] = [s for s in ai_suggestions
                             if not (isinstance(s, dict) and s.get("proposal_type") == "schedule")]
        ai_suggestions.append(proposal)
        state.update_task(task_id, ai_proposed=True, ai_suggestions=ai_suggestions,
                          created_by="ai_agent")
        event_bus.emit(AppEvent(
            type=EventType.AI_PROPOSAL_CREATED,
            data={"task_id": task_id, "title": task.title,
                  "proposal_type": "schedule", "schedule_data": proposal},
        ))
        return json.dumps({
            "task_id": task_id,
            "title": task.title,
            "proposed_schedule": proposal,
            "action": "proposed",
            "confirm_needed": True,
        }, ensure_ascii=False)
    except Exception as e:
        return f"[Error] 排程失败: {e}"


@tool
def acceptance_review(task_id: str, recommendation: str,
                       reason: str = "") -> str:
    """对验收中（inspection）的任务给出审核建议。结果以幽灵卡片展示，需人工确认。

    Args:
        task_id: 任务 ID
        recommendation: 审核建议 — "approve"（同意验收→移至已完成）或
                       "reject"（驳回→返回待处理）
        reason: 审核理由说明

    Returns:
        审核结果
    """
    valid_recs = {"approve", "reject"}
    if recommendation not in valid_recs:
        return f"[Error] 无效建议 '{recommendation}'，可选: approve, reject"

    task = state.get_task(task_id)
    if not task:
        return f"[Error] 任务 {task_id} 不存在"

    if task.status.value != "inspection":
        return (f"[Error] 任务 {task_id} 当前状态为 '{task.status.value}'，"
                f"只能审核验收中任务")

    state.update_task(task_id,
        ai_proposed=True, created_by="ai_agent",
        ai_acceptance_recommendation=recommendation,
        ai_acceptance_reason=reason,
    )

    # 发射幽灵提案事件
    event_bus.emit(AppEvent(
        type=EventType.AI_PROPOSAL_CREATED,
        data={
            "task_id": task_id,
            "title": task.title,
            "proposal_type": "acceptance",
            "recommendation": recommendation,
            "reason": reason,
        },
    ))

    labels = {"approve": "同意验收 → 已完成", "reject": "驳回 → 待处理"}
    return json.dumps({
        "task_id": task_id,
        "title": task.title,
        "recommendation": recommendation,
        "action": labels.get(recommendation, recommendation),
        "reason": reason,
        "confirm_needed": True,
    }, ensure_ascii=False)
