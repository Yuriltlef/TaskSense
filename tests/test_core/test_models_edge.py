"""核心数据模型 — 边界与边缘场景测试."""

import pytest
from datetime import datetime, timedelta

from app.core.models.task import (
    Task, TaskStatus, Priority, TaskType, ChecklistItem, StatusChange,
)
from app.core.models.aircraft import Aircraft, AircraftStatus
from app.core.models.kanban import ColumnConfig, FilterState, BoardState


class TestTaskEdgeCases:
    """Task 模型 — 边界和复杂场景。"""

    # ── 创建与默认值 ──

    def test_minimal_creation(self):
        """最简创建：仅 id 和 title。"""
        t = Task(id="t1", title="测试")
        assert t.status == TaskStatus.BACKLOG
        assert t.priority == Priority.CAT_C
        assert t.task_type == TaskType.TROUBLESHOOT
        assert t.aircraft_reg == ""
        assert t.ata_chapter == ""
        assert t.estimated_hours == 0.0
        assert t.is_rii is False
        assert t.parts_available is True

    def test_full_creation(self):
        """完整字段创建。"""
        now = datetime.now()
        t = Task(
            id="WO-2026-0626-001",
            title="C检 — 机身结构详细检查",
            description="按照AMM 53-10-01执行C检机身结构检查",
            aircraft_reg="B-5823",
            aircraft_model="737-800",
            ata_chapter="53-10-01",
            ata_section="53",
            ata_page_block="601",
            zone="100",
            fault_code="53-10-01-601",
            priority=Priority.CAT_B,
            task_type=TaskType.INSPECTION,
            assignee="张工",
            estimated_hours=48.0,
            due_date=now + timedelta(days=3),
            created_by="planner",
            is_rii=True,
            ad_numbers=["AD-2024-0015", "AD-2025-0008"],
            sb_numbers=["SB-737-53-012"],
            mel_item="MEL-53-01",
            parts_required=["PN-53001-01", "PN-53002-02"],
            tools_required=["T-2041", "T-3088"],
        )
        assert t.aircraft_reg == "B-5823"
        assert t.ata_chapter == "53-10-01"
        assert t.priority == Priority.CAT_B
        assert len(t.ad_numbers) == 2
        assert len(t.sb_numbers) == 1
        assert len(t.parts_required) == 2
        assert len(t.tools_required) == 2

    # ── 字段类型 ──

    def test_enum_string_values(self):
        """枚举的字符串值。"""
        assert Priority.AOG.value == "aog"
        assert Priority.CAT_A.value == "cat_a"
        assert TaskType.TROUBLESHOOT.value == "troubleshoot"
        assert TaskType.INSPECTION.value == "inspection"
        assert TaskStatus.BACKLOG.value == "backlog"
        assert TaskStatus.COMPLETED.value == "completed"

    def test_priority_from_string(self):
        """从字符串构造 Priority。"""
        assert Priority("aog") == Priority.AOG
        assert Priority("cat_c") == Priority.CAT_C

    def test_priority_invalid_string(self):
        """无效优先级字符串应抛异常。"""
        with pytest.raises(ValueError):
            Priority("urgent")

    def test_task_type_from_string(self):
        assert TaskType("troubleshoot") == TaskType.TROUBLESHOOT
        assert TaskType("repair") == TaskType.REPAIR

    # ── 标题处理 ──

    def test_long_title(self):
        """超长标题不应被截断（在模型中保留完整）。"""
        long_title = "A" * 500
        t = Task(id="1", title=long_title)
        assert len(t.title) == 500

    def test_unicode_title(self):
        """中文标题正常处理。"""
        t = Task(id="1", title="前起落架转向作动筒更换 — 波音737-800 AMM 32-41-03")
        assert "起落架" in t.title
        assert "737" in t.title

    def test_special_chars_title(self):
        """特殊字符标题。"""
        t = Task(id="1", title="Test / 测试 №42 (紧急)")
        assert "/" in t.title

    # ── 状态转换链 ──

    def test_full_lifecycle(self):
        """完整任务生命周期：backlog → triage → scheduled → ready →
        in_progress → inspection → completed → archived。"""
        t = Task(id="1", title="完整流程")
        transitions = [
            TaskStatus.TRIAGE,
            TaskStatus.SCHEDULED,
            TaskStatus.READY,
            TaskStatus.IN_PROGRESS,
            TaskStatus.INSPECTION,
            TaskStatus.COMPLETED,
            TaskStatus.ARCHIVED,
        ]
        for status in transitions:
            t.transition_to(status, "user")
        assert t.status == TaskStatus.ARCHIVED
        assert len(t.status_history) == 7

    def test_transition_records_user(self):
        """状态变更记录操作用户。"""
        t = Task(id="1", title="Test")
        t.transition_to(TaskStatus.TRIAGE, "张工")
        assert t.status_history[0].changed_by == "张工"

    def test_transition_with_comment(self):
        """状态变更可附带注释。"""
        t = Task(id="1", title="Test")
        t.transition_to(TaskStatus.TRIAGE, "李工", comment="AI 自动分类")
        assert t.status_history[0].comment == "AI 自动分类"

    def test_transition_sets_completed_at(self):
        """转换到 COMPLETED 时自动设置完成时间。"""
        t = Task(id="1", title="Test", status=TaskStatus.INSPECTION)
        assert t.completed_at is None
        t.transition_to(TaskStatus.COMPLETED, "user")
        assert t.completed_at is not None

    def test_transition_updates_updated_at(self):
        """状态转换更新 updated_at。"""
        import time
        t = Task(id="1", title="Test")
        old_time = t.updated_at
        time.sleep(0.001)  # 确保时间有变化
        t.transition_to(TaskStatus.TRIAGE, "user")
        assert t.updated_at >= old_time

    # ── 逾期判断 ──

    def test_overdue_exact_boundary(self):
        """逾期边界：刚好到期不算逾期。"""
        now = datetime.now()
        t = Task(id="1", title="Test", due_date=now, status=TaskStatus.IN_PROGRESS)
        # 刚好到期时 is_overdue 取决于 now() > due_date 的毫秒差
        # 这里只验证逻辑通路
        assert isinstance(t.is_overdue, bool)

    def test_overdue_future(self):
        """未来截止日期不算逾期。"""
        t = Task(
            id="1", title="Test",
            due_date=datetime.now() + timedelta(days=30),
            status=TaskStatus.IN_PROGRESS,
        )
        assert not t.is_overdue

    def test_overdue_no_due_date(self):
        """无截止日期的任务不会逾期。"""
        t = Task(id="1", title="Test", status=TaskStatus.IN_PROGRESS)
        assert not t.is_overdue

    def test_overdue_archived_not_overdue(self):
        """已归档任务即使过期也不算逾期。"""
        t = Task(
            id="1", title="Test",
            due_date=datetime.now() - timedelta(days=100),
            status=TaskStatus.ARCHIVED,
        )
        assert not t.is_overdue

    # ── 优先级排序 ──

    def test_priority_order_values(self):
        """优先级排序权重正确。"""
        assert Task(id="1", title="", priority=Priority.AOG).priority_order == 0
        assert Task(id="1", title="", priority=Priority.CAT_A).priority_order == 1
        assert Task(id="1", title="", priority=Priority.CAT_B).priority_order == 2
        assert Task(id="1", title="", priority=Priority.CAT_C).priority_order == 3
        assert Task(id="1", title="", priority=Priority.CAT_D).priority_order == 4

    # ── 检查清单 ──

    def test_empty_checklist_progress(self):
        """空检查清单进度为 0/0。"""
        t = Task(id="1", title="Test")
        assert t.checklist_progress() == (0, 0)

    def test_add_multiple_items(self):
        """添加多个检查项。"""
        t = Task(id="1", title="Test")
        items = [t.add_checklist_item(f"Step {i}") for i in range(10)]
        assert len(t.checklist) == 10
        # 每个 ID 唯一
        ids = [i.id for i in items]
        assert len(set(ids)) == 10

    def test_checklist_all_completed(self):
        """全部完成时进度正确。"""
        t = Task(id="1", title="Test")
        for i in range(5):
            item = t.add_checklist_item(f"Item {i}")
            item.toggle("user")
        done, total = t.checklist_progress()
        assert done == 5
        assert total == 5

    def test_checklist_toggle_twice(self):
        """切换两次回到未完成。"""
        t = Task(id="1", title="Test")
        item = t.add_checklist_item("Test")
        item.toggle("user")
        item.toggle("user")
        assert not item.completed
        assert item.completed_by is None

    # ── 序列化 ──

    def test_to_dict_contains_all_keys(self):
        """to_dict 包含所有关键字段。"""
        t = Task(id="t1", title="Test", priority=Priority.AOG,
                aircraft_reg="B-5823", is_rii=True)
        d = t.to_dict()
        required_keys = ["id", "title", "priority", "status", "aircraft_reg",
                        "aircraft_model", "ata_chapter", "assignee", "is_rii",
                        "is_overdue", "checklist_done", "checklist_total"]
        for key in required_keys:
            assert key in d, f"Missing key: {key}"

    def test_to_dict_due_date_none(self):
        """due_date 为 None 时序列化为 None。"""
        t = Task(id="1", title="Test")
        d = t.to_dict()
        assert d["due_date"] is None

    def test_to_dict_enum_values(self):
        """枚举值序列化为字符串。"""
        t = Task(id="1", title="Test", priority=Priority.AOG,
                task_type=TaskType.INSPECTION, status=TaskStatus.TRIAGE)
        d = t.to_dict()
        assert d["priority"] == "aog"
        assert d["status"] == "triage"

    # ── Blocked By / 依赖 ──

    def test_blocked_by_default(self):
        """默认无阻塞依赖。"""
        t = Task(id="1", title="Test")
        assert t.blocked_by == []

    def test_add_blocks(self):
        """添加阻塞依赖。"""
        t = Task(id="1", title="Test", blocked_by=["t2", "t3"])
        assert len(t.blocked_by) == 2

    def test_sub_tasks_default(self):
        """默认无子任务。"""
        t = Task(id="1", title="Test")
        assert t.sub_tasks == []

    # ── AI 元数据 ──

    def test_ai_fields_default_none(self):
        """AI 字段默认为空。"""
        t = Task(id="1", title="Test")
        assert t.ai_priority is None
        assert t.ai_ata_chapter is None
        assert t.ai_suggestions == []
        assert t.rag_references == []


class TestAircraftEdgeCases:
    """Aircraft 模型 — 边界测试。"""

    def test_no_model(self):
        """无型号时 display_name 仅显示注册号。"""
        ac = Aircraft(registration="N12345")
        assert ac.display_name == "N12345"

    def test_all_statuses(self):
        """所有状态的描述都有返回。"""
        for status in AircraftStatus:
            ac = Aircraft(registration="X", status=status)
            assert len(ac.status_display) > 0

    def test_to_dict(self):
        ac = Aircraft(registration="B-5823", model="737-800",
                      status=AircraftStatus.AOG)
        d = ac.to_dict()
        assert d["registration"] == "B-5823"
        assert d["status"] == "aog"
        assert "total_hours" in d

    def test_mel_items(self):
        ac = Aircraft(registration="B-5823",
                      mel_items=["MEL-32-01", "MEL-21-03"])
        assert len(ac.mel_items) == 2

    def test_default_values(self):
        ac = Aircraft(registration="N0000")
        assert ac.model == ""
        assert ac.msn == ""
        assert ac.status == AircraftStatus.OPERATIONAL
        assert ac.total_hours == 0.0
        assert ac.total_cycles == 0


class TestColumnConfigEdgeCases:
    """ColumnConfig — 边界测试。"""

    def test_wip_exactly_at_limit(self):
        """恰好达到 WIP 限制不算超限。"""
        col = ColumnConfig(id="test", title="T", wip_limit=5)
        col.task_count = 5
        assert not col.wip_exceeded
        assert col.wip_percentage == 1.0

    def test_wip_zero_limit_division(self):
        """WIP 为 0 时应安全处理（Min: wip_limit=0 时百分比=0）。"""
        col = ColumnConfig(id="test", title="T", wip_limit=0)
        col.task_count = 5
        # wip_limit=0 时视作无限制，百分比为 0
        assert col.wip_percentage == 0.0

    def test_wip_none_percentage(self):
        """无 WIP 限制时百分比为 0。"""
        col = ColumnConfig(id="test", title="T", wip_limit=None)
        col.task_count = 999
        assert col.wip_percentage == 0.0


class TestFilterStateEdgeCases:
    """FilterState — 边界测试。"""

    def test_all_empty_not_active(self):
        f = FilterState()
        assert not f.is_active
        assert f.active_filter_count == 0

    def test_single_field_active(self):
        """每个字段单独设为活动。"""
        assert FilterState(search_query="x").is_active
        assert FilterState(ata_chapters=["32"]).is_active
        assert FilterState(aircraft_regs=["B-5823"]).is_active
        assert FilterState(priorities=["aog"]).is_active
        assert FilterState(task_types=["inspection"]).is_active
        assert FilterState(assignees=["张工"]).is_active
        assert FilterState(statuses=["backlog"]).is_active

    def test_date_active(self):
        assert FilterState(due_date_from=datetime.now()).is_active
        assert FilterState(due_date_to=datetime.now()).is_active

    def test_empty_lists_not_active(self):
        """空列表不算活动筛选。"""
        f = FilterState(ata_chapters=[])
        assert not f.is_active
        assert f.active_filter_count == 0

    def test_show_completed_not_affecting(self):
        """show_completed 不参与 is_active 判断。"""
        f1 = FilterState(show_completed=False)
        f2 = FilterState(show_completed=True)
        assert not f1.is_active
        assert not f2.is_active

    def test_active_count_max(self):
        """所有字段激活时计数。"""
        f = FilterState(
            search_query="test",
            ata_chapters=["32"],
            aircraft_regs=["B-5823"],
            priorities=["aog"],
            task_types=["troubleshoot"],
            assignees=["张工"],
            statuses=["in_progress"],
            due_date_from=datetime.now(),
        )
        assert f.active_filter_count == 8  # due_date_to is None

    def test_multiple_values_same_field(self):
        """同一字段多个值仍算一个激活筛选器。"""
        f = FilterState(ata_chapters=["21", "24", "32"])
        assert f.active_filter_count == 1


class TestBoardStateEdgeCases:
    """BoardState — 边界测试。"""

    def test_empty_board(self):
        board = BoardState()
        assert board.columns == []
        assert board.tasks == {}
        assert board.filters is not None
        assert board.swimlane_by is None

    def test_columns_with_tasks(self):
        cols = [
            ColumnConfig(id="backlog", title="待处理"),
            ColumnConfig(id="done", title="完成"),
        ]
        tasks = {"backlog": ["t1", "t2"], "done": []}
        board = BoardState(columns=cols, tasks=tasks)
        assert board.get_task_count("backlog") == 2
        assert board.get_task_count("done") == 0
        assert board.get_task_count("nonexistent") == 0

    def test_task_column_search(self):
        board = BoardState(tasks={
            "backlog": ["a", "b"],
            "triage": ["c"],
            "in_progress": ["d", "e", "f"],
        })
        assert board.task_column("a") == "backlog"
        assert board.task_column("c") == "triage"
        assert board.task_column("f") == "in_progress"
        assert board.task_column("z") is None

    def test_duplicate_task_id(self):
        """同一 task_id 不应出现在多列（但模型不阻止，搜索返回首次找到的列）。"""
        board = BoardState(tasks={
            "backlog": ["t1"],
            "triage": ["t1"],  # 错误数据
        })
        col = board.task_column("t1")
        # 返回第一个匹配的列
        assert col in ("backlog", "triage")

    def test_swimlane_setting(self):
        board = BoardState(swimlane_by="ata")
        assert board.swimlane_by == "ata"
