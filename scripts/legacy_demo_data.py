# -*- coding: utf-8 -*-
"""遗留演示数据生成器 — 已废弃，仅供参考。

当前数据统一由 data/board_state.json 管理。
使用 scripts/gen_demo_json.py 生成/重置 JSON。
"""

from datetime import datetime, timedelta


def load_demo_data(state, task_service):
    """加载演示数据（已废弃）。"""
    from app.core.models.aircraft import Aircraft, AircraftStatus

    # 演示飞机
    demo_aircraft = [
        Aircraft(registration="B-5823", model="737-800", msn="39999",
                 status=AircraftStatus.IN_MAINTENANCE, total_hours=28500,
                 current_location="Hangar 3", open_defects=3),
        Aircraft(registration="B-2518", model="A320neo", msn="8876",
                 status=AircraftStatus.OPERATIONAL, total_hours=12400,
                 current_location="Gate A12"),
        Aircraft(registration="B-9076", model="A330-300", msn="1503",
                 status=AircraftStatus.AOG, total_hours=32100,
                 current_location="Hangar 1", open_defects=1),
    ]
    for ac in demo_aircraft:
        state.add_aircraft(ac)

    now = datetime.now()
    demos = [
        ("backlog", "APU 启动时间超限检查", "B-5823", "49-11-01", "aog"),
        ("backlog", "右发滑油消耗率偏高", "B-9076", "79-21-01", "aog"),
        ("backlog", "客舱空调出风口异响", "B-2518", "21-51-01", "cat_c"),
        ("triage", "前起落架转向异响排查", "B-5823", "32-41-03", "cat_a"),
        ("triage", "左发 N1 振动指示异常", "B-9076", "77-11-01", "cat_b"),
        ("scheduled", "A 检 — 飞行控制面检查", "B-5823", "27-10-00", "cat_b"),
        ("scheduled", "发动机滑油更换", "B-2518", "79-00-01", "cat_c"),
        ("ready", "机翼前缘防冰管路测试", "B-5823", "30-11-01", "cat_c"),
        ("ready", "APU 滑油勤务", "B-5823", "49-91-01", "cat_c"),
        ("in_progress", "起落架收放测试", "B-5823", "32-31-01", "cat_b"),
        ("in_progress", "右发燃油滤更换", "B-9076", "73-11-03", "cat_a"),
        ("inspection", "C 检 — 机身结构检查", "B-5823", "53-10-01", "cat_c"),
        ("parts_hold", "左发点火电嘴更换", "B-9076", "74-11-03", "cat_a"),
        ("completed", "驾驶舱仪表灯光检查", "B-2518", "33-11-01", "cat_d"),
        ("completed", "APU 进气门清洁", "B-5823", "49-11-01", "cat_d"),
    ]

    for col_id, title, reg, ata, pri in demos:
        offset = {"backlog": 0, "triage": 1, "scheduled": 2,
                  "ready": 3, "in_progress": 4, "inspection": 5,
                  "parts_hold": 6, "completed": 7}.get(col_id, 0)

        task = task_service.create_task(
            title=title,
            description=f"{title} — 演示任务。ATA {ata}，飞机 {reg}。",
            aircraft_reg=reg,
            ata_chapter=ata,
            priority=pri,
            task_type="troubleshoot" if "排查" in title or "异常" in title
            else "inspection" if "检查" in title
            else "servicing" if "更换" in title or "勤务" in title
            else "test" if "测试" in title
            else "repair",
            assignee=["张工", "李工", "王工", "赵工"][offset % 4],
            estimated_hours=[2, 4, 6, 1.5, 8][offset % 5],
            due_date=now + timedelta(hours=[2, 4, 24, 48, 72][offset % 5]),
            zone=["710", "420", "310", "510", "110"][offset % 5],
        )

        if task and col_id != "backlog":
            try:
                status_order = ["backlog", "triage", "scheduled", "ready",
                               "in_progress", "inspection", "parts_hold", "completed"]
                current_idx = status_order.index(col_id)
                for i in range(1, current_idx + 1):
                    mid_status = status_order[i]
                    if mid_status == "parts_hold":
                        task.parts_available = False
                        task.parts_required = ["PN-32041-05"]
                    task_service.move_task(task.id, mid_status, changed_by="demo")
            except Exception:
                pass

    return len(demos)
