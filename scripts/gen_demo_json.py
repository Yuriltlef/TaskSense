"""Generate board_state.json from demo data."""
import json, os, sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.state import state
from app.core.services.task_service import task_service
from app.core.models.aircraft import Aircraft, AircraftStatus

# Clean state
state._tasks.clear()
state._task_order = {c: [] for c in state._task_order}

# Demo aircraft
for ac in [
    Aircraft(registration="B-5823", model="737-800", msn="39999",
             status=AircraftStatus.IN_MAINTENANCE, total_hours=28500,
             current_location="Hangar 3", open_defects=3, overdue_tasks_count=1),
    Aircraft(registration="B-2518", model="A320neo", msn="8876",
             status=AircraftStatus.OPERATIONAL, total_hours=12400,
             current_location="Gate A12"),
    Aircraft(registration="B-9076", model="A330-300", msn="1503",
             status=AircraftStatus.AOG, total_hours=32100,
             current_location="Hangar 1", open_defects=1),
]:
    state.add_aircraft(ac)

now = datetime.now()
demo_tasks = [
    ("backlog", "APU 启动时间超限检查", "B-5823", "49-11-01", "aog", "inspection", "张", 3.0, "310"),
    ("backlog", "右发滑油消耗率偏高", "B-9076", "79-21-01", "aog", "troubleshoot", "李", 5.0, "420"),
    ("backlog", "客舱空调出风口异响", "B-2518", "21-51-01", "cat_c", "troubleshoot", "王", 2.0, "510"),
    ("triage", "前起落架转向异响排查", "B-5823", "32-41-03", "cat_a", "troubleshoot", "张", 4.5, "710"),
    ("triage", "左发 N1 振动指示异常", "B-9076", "77-11-01", "cat_b", "troubleshoot", "赵", 6.0, "420"),
    ("scheduled", "A 检 — 飞行控制面功能检查", "B-5823", "27-10-00", "cat_b", "inspection", "李", 8.0, "210"),
    ("scheduled", "发动机滑油更换", "B-2518", "79-00-01", "cat_c", "servicing", "王", 2.0, "420"),
    ("ready", "机翼前缘防冰管路测试", "B-5823", "30-11-01", "cat_c", "test", "张", 4.0, "610"),
    ("ready", "APU 滑油勤务", "B-5823", "49-91-01", "cat_c", "servicing", "赵", 1.5, "310"),
    ("in_progress", "起落架收放功能测试", "B-5823", "32-31-01", "cat_b", "test", "张", 3.0, "710"),
    ("in_progress", "右发燃油滤更换", "B-9076", "73-11-03", "cat_a", "removal_install", "李", 4.0, "420"),
    # -- inspection tasks --
    ("inspection", "C 检 — 机身结构详细检查", "B-5823", "53-10-01", "cat_c", "inspection", "王", 48.0, "100"),
    ("inspection", "右发 N1 振动传感器更换", "B-9076", "77-11-01", "cat_a", "removal_install", "李", 2.5, "420"),
    ("inspection", "左大翼前缘凹坑修理", "B-5823", "57-40-01", "cat_b", "repair", "赵", 12.0, "610"),
    ("inspection", "客舱应急灯光系统检查", "B-2518", "33-51-01", "cat_c", "inspection", "张", 1.5, "510"),
    # -- rejection-bound tasks --
    ("inspection", "右发滑油渗漏修理", "B-9076", "79-21-01", "cat_a", "repair", "李", 6.0, "425"),
    ("inspection", "机翼前缘防冰管路测试", "B-5823", "30-11-01", "cat_a", "test", "赵", 3.0, "610"),
    ("inspection", "APU 排气温度超限排故", "B-5823", "49-11-01", "cat_a", "troubleshoot", "张", 8.0, "315"),
    ("inspection", "左发燃油泵更换", "B-9076", "73-11-01", "cat_a", "removal_install", "王", 5.0, "430"),
    ("parts_hold", "左发点火电嘴更换", "B-9076", "74-11-03", "cat_a", "removal_install", "赵", 3.0, "420"),
    ("completed", "驾驶舱仪表灯光检查", "B-2518", "33-11-01", "cat_d", "inspection", "李", 1.0, "110"),
    ("completed", "APU 进气门清洁", "B-5823", "49-11-01", "cat_d", "servicing", "张", 2.0, "310"),
]

TARGET_PATHS = {
    "backlog": [], "triage": ["triage"], "scheduled": ["triage", "scheduled"],
    "ready": ["triage", "scheduled", "ready"],
    "in_progress": ["triage", "scheduled", "ready", "in_progress"],
    "inspection": ["triage", "scheduled", "ready", "in_progress", "inspection"],
    "parts_hold": ["triage", "scheduled", "ready", "in_progress", "parts_hold"],
    "completed": ["triage", "scheduled", "ready", "in_progress", "completed"],
}
EMP_MAP = {"张": ("ZH001", "张工"), "李": ("ZH002", "李工"),
           "王": ("ZH003", "王工"), "赵": ("ZH004", "赵工")}
due_map = {"aog": 4, "cat_a": 24, "cat_b": 72, "cat_c": 168, "cat_d": 720}

for col_target, title, reg, ata, pri, ttype, who, hrs, zone in demo_tasks:
    eid, ename = EMP_MAP.get(who, ("", who))
    task = task_service.create_task(
        title=title, description=f"{title}。ATA {ata}，飞机 {reg}。",
        aircraft_reg=reg, ata_chapter=ata, priority=pri, task_type=ttype,
        assignee=who, employee_id=eid, employee_name=ename,
        estimated_hours=hrs, zone=zone,
        due_date=now + timedelta(hours=due_map.get(pri, 72)),
    )
    if not task:
        continue
    path = TARGET_PATHS.get(col_target, [])
    for mid in path:
        try:
            if mid == "parts_hold":
                task_service.update_task(task.id, parts_available=False,
                                         parts_required=["PN-REQUIRED"])
            task_service.move_task(task.id, mid, changed_by="demo")
        except Exception as ex:
            print(f"[GEN] move failed: {title} -> {mid}: {ex}")
    if col_target in ("scheduled", "ready", "in_progress", "inspection",
                      "parts_hold", "completed"):
        ps = now - timedelta(hours=hrs * 2)
        pe = now + timedelta(hours=hrs)
        task_service.update_task(task.id, planned_start=ps, planned_end=pe)

# Handover logs
LOGS = {
    "C 检 — 机身结构详细检查": (
        "【工作内容】按 C 检工卡完成机身结构详细检查。\n"
        "【检查范围】前机身 (STA 178-360)、中机身 (STA 360-727)、后机身 (STA 727-947)。\n"
        "【检查方法】目视检查 + 涡流探伤 (ET) 关键紧固件孔。\n"
        "【发现问题】STA 420 处长桁有一处 3mm 腐蚀坑，已按 SRM 53-00-01 打磨处理，"
        "剩余壁厚 1.27mm > 1.02mm 容差。\n"
        "【测量值】腐蚀坑深度 0.3mm，打磨区域 15x20mm，NDT 确认无裂纹。\n"
        "【工卡签署】全部 48 项检查已完成并签署。\n"
        "【工具清点】已清点，无遗漏。\n"
        "【备注】建议下次 C 检复查 STA 420 区域。"
    ),
    "右发 N1 振动传感器更换": "更换右发 N1 振动传感器，测试正常。",
    "左大翼前缘凹坑修理": (
        "【工作内容】左大翼前缘 STA 580 处凹坑修理。\n"
        "【修理方法】按 SRM 57-40-01 执行外修补贴片修理。\n"
        "【材料】2024-T3 铝板 0.063inch，Hi-Lok HL18-6 紧固件 x 8。\n"
        "【NDT】修理前后涡流探伤，无裂纹。\n"
        "【气动外形】修理后外形在 AMM 容差范围内。\n"
        "【备注】RII 项目，待检查员最终签署。"
    ),
    "客舱应急灯光系统检查": "",
    "右发滑油渗漏修理": "",
    "机翼前缘防冰管路测试": (
        "【工作内容】机翼前缘防冰管路压力测试。\n"
        "【测试结果】压力降至 85% 后保持稳定，略低于手册要求的 90%。\n"
        "【异常】3 号管路接头处有微量渗漏痕迹，未处理。\n"
        "【备注】因航班计划紧迫，建议先放行后续再排故。\n"
        "【RII】必检项目，检查员尚未签署。"
    ),
    "APU 排气温度超限排故": "排除了几个传感器，换了新的，感觉应该好了。试车时温度好像降了点。",
    "左发燃油泵更换": "换完了。",
}
RII_TASKS = {"左大翼前缘凹坑修理", "机翼前缘防冰管路测试"}

for t in state.get_all_tasks():
    if t.title in LOGS:
        updates = {"shift_handover_log": LOGS[t.title]}
        if t.title in RII_TASKS:
            updates["is_rii"] = True
            updates["inspector"] = "刘"
        task_service.update_task(t.id, **updates)

# Save via persistence service
os.makedirs("data", exist_ok=True)
from app.core.services.persistence_service import persistence_service
persistence_service.set_path("data/board_state.json")
persistence_service.save()
print(f"Saved {len(state.get_all_tasks())} tasks to data/board_state.json")
insp_tasks = [t for t in state.get_all_tasks() if t.status.value == "inspection"]
print(f"Inspection tasks: {len(insp_tasks)}")
for t in insp_tasks:
    print(f"  {t.id}: {t.title} | log={'有' if t.shift_handover_log else '无'} | rii={t.is_rii}")
