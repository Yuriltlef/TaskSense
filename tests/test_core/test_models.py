"""核心数据模型测试."""

import pytest
from datetime import datetime, timedelta

from app.core.models.task import (
    Task, TaskStatus, Priority, TaskType, ChecklistItem, StatusChange,
)
from app.core.models.aircraft import Aircraft, AircraftStatus
from app.core.models.kanban import ColumnConfig, FilterState, BoardState


class TestTask:
    """Task 模型测试。"""

    def test_create_task(self):
        task = Task(
            id="test-001",
            title="起落架异响排查",
            aircraft_reg="B-5823",
            ata_chapter="32-41-03",
            priority=Priority.CAT_A,
        )
        assert task.id == "test-001"
        assert task.title == "起落架异响排查"
        assert task.priority == Priority.CAT_A
        assert task.status == TaskStatus.BACKLOG  # 默认状态

    def test_priority_order(self):
        task_aog = Task(id="1", title="Test", priority=Priority.AOG)
        task_catd = Task(id="2", title="Test", priority=Priority.CAT_D)
        assert task_aog.priority_order < task_catd.priority_order

    def test_transition(self):
        task = Task(id="1", title="Test")
        task.transition_to(TaskStatus.TRIAGE, "user")
        assert task.status == TaskStatus.TRIAGE
        assert len(task.status_history) == 1
        assert task.status_history[0].from_status == TaskStatus.BACKLOG
        assert task.status_history[0].to_status == TaskStatus.TRIAGE

    def test_is_overdue(self):
        task = Task(
            id="1", title="Test",
            due_date=datetime.now() - timedelta(hours=1),
            status=TaskStatus.IN_PROGRESS,
        )
        assert task.is_overdue

    def test_not_overdue_when_completed(self):
        task = Task(
            id="1", title="Test",
            due_date=datetime.now() - timedelta(hours=1),
            status=TaskStatus.COMPLETED,
        )
        assert not task.is_overdue

    def test_checklist_progress(self):
        task = Task(id="1", title="Test")
        task.add_checklist_item("检查项 A")
        task.add_checklist_item("检查项 B")
        task.add_checklist_item("检查项 C")

        done, total = task.checklist_progress()
        assert done == 0
        assert total == 3

        task.checklist[0].toggle("user")
        done, total = task.checklist_progress()
        assert done == 1
        assert total == 3

    def test_checklist_toggle(self):
        task = Task(id="1", title="Test")
        item = task.add_checklist_item("检查项")
        assert not item.completed

        item.toggle("张工")
        assert item.completed
        assert item.completed_by == "张工"
        assert item.completed_at is not None

        item.toggle("张工")
        assert not item.completed
        assert item.completed_by is None

    def test_to_dict(self):
        task = Task(
            id="test-001",
            title="测试任务",
            aircraft_reg="B-5823",
            priority=Priority.AOG,
        )
        d = task.to_dict()
        assert d["id"] == "test-001"
        assert d["title"] == "测试任务"
        assert d["priority"] == "aog"
        assert d["status"] == "backlog"


class TestAircraft:
    """Aircraft 模型测试。"""

    def test_create_aircraft(self):
        ac = Aircraft(registration="B-5823", model="737-800")
        assert ac.registration == "B-5823"
        assert ac.status == AircraftStatus.OPERATIONAL

    def test_display_name(self):
        ac = Aircraft(registration="B-5823", model="737-800")
        assert "B-5823" in ac.display_name
        assert "737-800" in ac.display_name

    def test_status_display(self):
        ac = Aircraft(registration="B-5823", status=AircraftStatus.AOG)
        assert "AOG" in ac.status_display


class TestColumnConfig:
    """ColumnConfig 测试。"""

    def test_wip_limit(self):
        col = ColumnConfig(id="in_progress", title="执行中", wip_limit=10)
        col.task_count = 5
        assert not col.wip_exceeded
        col.task_count = 12
        assert col.wip_exceeded

    def test_no_wip(self):
        col = ColumnConfig(id="backlog", title="待处理", wip_limit=None)
        col.task_count = 100
        assert not col.wip_exceeded

    def test_wip_percentage(self):
        col = ColumnConfig(id="test", title="Test", wip_limit=10)
        col.task_count = 7
        assert col.wip_percentage == 0.7


class TestFilterState:
    """FilterState 测试。"""

    def test_default_not_active(self):
        f = FilterState()
        assert not f.is_active

    def test_search_active(self):
        f = FilterState(search_query="test")
        assert f.is_active

    def test_ata_filter_active(self):
        f = FilterState(ata_chapters=["32"])
        assert f.is_active

    def test_active_count(self):
        f = FilterState(
            search_query="test",
            ata_chapters=["32"],
            priorities=["aog"],
        )
        assert f.active_filter_count == 3


class TestBoardState:
    """BoardState 测试。"""

    def test_get_task_ids(self):
        state = BoardState(
            tasks={"backlog": ["t1", "t2"], "triage": ["t3"]}
        )
        assert state.get_task_ids("backlog") == ["t1", "t2"]
        assert state.get_task_ids("triage") == ["t3"]
        assert state.get_task_ids("unknown") == []

    def test_get_task_count(self):
        state = BoardState(tasks={"backlog": ["t1", "t2", "t3"]})
        assert state.get_task_count("backlog") == 3

    def test_task_column(self):
        state = BoardState(tasks={
            "backlog": ["t1", "t2"],
            "triage": ["t3"],
        })
        assert state.task_column("t1") == "backlog"
        assert state.task_column("t3") == "triage"
        assert state.task_column("t999") is None
