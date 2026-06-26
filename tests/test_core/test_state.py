"""状态管理器测试."""

import pytest

from app.core.models.kanban import ColumnConfig
from app.core.models.task import Task, TaskStatus, Priority
from app.core.state import AppState
from app.core.validators import BusinessRuleError, TaskValidators


class TestAppState:
    """AppState 测试。"""

    @pytest.fixture
    def state(self):
        """每个测试使用独立的 AppState。"""
        s = AppState()
        return s

    def test_initial_columns(self, state):
        columns = state.get_columns()
        col_ids = [c.id for c in columns]
        assert "backlog" in col_ids
        assert "triage" in col_ids
        assert "in_progress" in col_ids
        assert "completed" in col_ids

    def test_create_task(self, state):
        task = state.create_task(title="测试任务", aircraft_reg="B-5823")
        assert task.id is not None
        assert task.title == "测试任务"
        assert task.status == TaskStatus.BACKLOG

        # 验证任务出现在 backlog 列
        tasks = state.get_tasks_by_column("backlog")
        assert len(tasks) == 1
        assert tasks[0].id == task.id

    def test_get_task(self, state):
        task = state.create_task(title="Test")
        retrieved = state.get_task(task.id)
        assert retrieved is not None
        assert retrieved.title == "Test"

        assert state.get_task("nonexistent") is None

    def test_update_task(self, state):
        task = state.create_task(title="原始标题")
        updated = state.update_task(task.id, title="新标题", priority=Priority.AOG)
        assert updated.title == "新标题"
        assert updated.priority == Priority.AOG

    def test_move_task(self, state):
        task = state.create_task(title="Test")
        moved = state.move_task(task.id, "triage", changed_by="test_user")

        assert moved is not None
        assert moved.status == TaskStatus.TRIAGE
        assert len(moved.status_history) == 1

        # 验证任务不在原列
        backlog_tasks = state.get_tasks_by_column("backlog")
        assert task.id not in [t.id for t in backlog_tasks]

        # 验证任务在新列
        triage_tasks = state.get_tasks_by_column("triage")
        assert task.id in [t.id for t in triage_tasks]

    def test_delete_task(self, state):
        task = state.create_task(title="Test")
        assert state.delete_task(task.id)
        assert state.get_task(task.id) is None

        backlog_tasks = state.get_tasks_by_column("backlog")
        assert task.id not in [t.id for t in backlog_tasks]

    def test_delete_nonexistent(self, state):
        assert not state.delete_task("nonexistent")

    def test_multiple_tasks_order(self, state):
        t1 = state.create_task(title="First")
        t2 = state.create_task(title="Second")
        t3 = state.create_task(title="Third")

        tasks = state.get_tasks_by_column("backlog")
        task_ids = [t.id for t in tasks]
        # 新任务插入到最前面
        assert task_ids.index(t3.id) < task_ids.index(t2.id) < task_ids.index(t1.id)

    def test_subscribe(self, state):
        notified = []

        def listener():
            notified.append(True)

        state.subscribe(listener)
        state.create_task(title="Test")
        assert len(notified) == 1

    def test_get_board_state(self, state):
        state.create_task(title="Test")
        board = state.get_board_state()

        assert len(board.columns) > 0
        assert "backlog" in board.tasks
        assert len(board.tasks["backlog"]) == 1

    def test_filters(self, state):
        task = state.create_task(title="起落架排查", ata_chapter="32-41-03")
        from app.core.models.kanban import FilterState
        state.set_filters(FilterState(search_query="起落架"))

        board = state.get_board_state()
        # 应该能搜索到
        assert task.id in board.tasks.get("backlog", [])

    def test_stats(self, state):
        state.create_task(title="Test 1", priority=Priority.AOG)
        state.create_task(title="Test 2", priority=Priority.CAT_C)
        state.create_task(title="Test 3", priority=Priority.CAT_D)

        stats = state.get_stats()
        assert stats["total"] == 3
        assert stats["backlog"] == 3
        assert stats["aog_count"] == 1


class TestValidators:
    """校验器测试。"""

    def test_validate_create_title_required(self):
        with pytest.raises(BusinessRuleError, match="标题不能为空"):
            TaskValidators.validate_create("")

    def test_validate_create_title_too_long(self):
        with pytest.raises(BusinessRuleError, match="不能超过200"):
            TaskValidators.validate_create("x" * 201)

    def test_validate_create_ok(self):
        # 不应抛异常
        TaskValidators.validate_create("正常标题", "B-5823")

    def test_validate_transition_allowed(self):
        from app.core.models.kanban import ColumnConfig

        task = Task(id="1", title="Test", status=TaskStatus.BACKLOG)
        columns = [
            ColumnConfig(id="backlog", title="待处理"),
            ColumnConfig(id="triage", title="分类中"),
            ColumnConfig(id="scheduled", title="已排程"),
        ]
        # backlog → triage 是允许的
        TaskValidators.validate_transition(task, "triage", columns)

    def test_validate_transition_not_allowed(self):
        from app.core.models.kanban import ColumnConfig

        task = Task(id="1", title="Test", status=TaskStatus.BACKLOG)
        columns = [
            ColumnConfig(id="backlog", title="待处理"),
            ColumnConfig(id="completed", title="已完成"),
        ]
        # backlog → completed 不被允许
        with pytest.raises(BusinessRuleError, match="不允许"):
            TaskValidators.validate_transition(task, "completed", columns)

    def test_validate_wip_normal(self):
        col = ColumnConfig(id="test", title="Test", wip_limit=10)
        col.task_count = 5
        assert TaskValidators.validate_wip(col) is None

    def test_validate_wip_exceeded(self):
        col = ColumnConfig(id="test", title="Test", wip_limit=10)
        col.task_count = 10
        warning = TaskValidators.validate_wip(col)
        assert warning is not None
        assert "WIP" in warning
