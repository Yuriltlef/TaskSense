"""Agent 工具 — 看板操作."""

from langchain.tools import tool

from app.core.state import state
from app.core.services.task_service import task_service
from app.core.services.board_service import board_service


@tool
def get_board_summary() -> str:
    """获取当前看板状态摘要：各列任务数、优先级分布、逾期情况。"""
    stats = board_service.get_stats()
    fleet = board_service.get_fleet_summary()

    return (
        f"看板摘要:\n"
        f"- 总任务: {stats.get('total', 0)}\n"
        f"- AOG 紧急: {stats.get('aog_count', 0)}\n"
        f"- 逾期: {stats.get('overdue', 0)}\n"
        f"- 待处理: {stats.get('backlog', 0)}\n"
        f"- 执行中: {stats.get('in_progress', 0)}\n"
        f"- 已完成: {stats.get('completed', 0)}\n"
        f"机队: 总计 {fleet.get('total', 0)}, AOG {fleet.get('aog', 0)}, "
        f"维修中 {fleet.get('in_maintenance', 0)}"
    )


@tool
def get_task_detail(task_id: str) -> str:
    """获取指定任务的完整详情。

    Args:
        task_id: 任务 ID
    """
    t = state.get_task(task_id)
    if not t:
        return f"任务 {task_id} 不存在"

    parts = [
        f"任务: {t.title}",
        f"ID: {t.id}",
        f"状态: {t.status.value}",
        f"优先级: {t.priority.value}",
        f"ATA 章节: {t.ata_chapter}",
        f"飞机: {t.aircraft_reg} · {t.aircraft_model}",
        f"负责人: {t.assignee or '未分配'}",
        f"预估工时: {t.estimated_hours}h",
        f"截止: {t.due_date.strftime('%Y-%m-%d %H:%M') if t.due_date else '无'}",
    ]
    if t.is_overdue:
        parts.append("⚠ 已逾期")
    if t.is_rii:
        parts.append("🔴 必检项目 (RII)")
    if t.ad_numbers:
        parts.append(f"AD: {', '.join(t.ad_numbers)}")

    return "\n".join(parts)


@tool
def search_related_tasks(ata_chapter: str) -> str:
    """搜索与指定 ATA 章节相关的所有任务。

    Args:
        ata_chapter: ATA 章节号（如 "32-41-03"）。只输入前两位（如 "32"）可查该章。
    """
    all_tasks = state.get_all_tasks()
    section = ata_chapter.split("-")[0]
    related = [t for t in all_tasks
               if t.ata_chapter.startswith(ata_chapter)
               or t.ata_section == section]

    if not related:
        return f"未找到与 ATA {ata_chapter} 相关的任务"

    lines = [f"找到 {len(related)} 个相关任务:"]
    for t in related[:10]:
        lines.append(
            f"  [{t.id}] {t.title} | {t.status.value} | "
            f"{t.aircraft_reg} | {t.priority.value}"
        )
    return "\n".join(lines)


@tool
def search_employees(query: str = "") -> str:
    """搜索员工信息。可按 ID、姓名或工种搜索。

    Args:
        query: 搜索关键词。为空时返回全部可用员工。
    """
    from app.core.services.employee_service import employee_service
    employee_service._ensure_loaded()

    if query:
        results = employee_service.search_employees(query)
    else:
        results = employee_service.get_available_employees()

    if not results:
        return "未找到匹配的员工"

    lines = [f"找到 {len(results)} 名员工:"]
    for e in results[:20]:
        avail = "可用" if e.get("available", True) else "不可用"
        certs = ", ".join(e.get("certifications", []))
        lines.append(
            f"  {e['employee_id']} | {e['name']} | {e.get('trade', '')} | "
            f"{avail} | 机型: {certs}"
        )
    return "\n".join(lines)
