"""业务服务层测试."""

import pytest

from app.core.models.task import TaskStatus, Priority
from app.core.services.task_service import TaskService
from app.core.services.board_service import BoardService
from app.core.validators import BusinessRuleError


class TestTaskService:
    """TaskService 测试。"""

    @pytest.fixture
    def service(self):
        return TaskService()

    def test_create_task(self, service):
        task = service.create_task(
            title="起落架排故",
            aircraft_reg="B-5823",
            ata_chapter="32-41-03",
            priority="cat_a",
        )
        assert task.title == "起落架排故"
        assert task.aircraft_reg == "B-5823"
        assert task.priority == Priority.CAT_A
        assert task.status == TaskStatus.BACKLOG

    def test_create_task_empty_title_raises(self, service):
        with pytest.raises(BusinessRuleError):
            service.create_task(title="")

    def test_move_task_valid(self, service):
        task = service.create_task(title="Test")
        moved = service.move_task(task.id, "triage")
        assert moved.status == TaskStatus.TRIAGE

    def test_move_task_invalid_raises(self, service):
        task = service.create_task(title="Test")
        with pytest.raises(BusinessRuleError):
            # backlog → completed 不允许
            service.move_task(task.id, "completed")

    def test_move_nonexistent_raises(self, service):
        with pytest.raises(BusinessRuleError, match="不存在"):
            service.move_task("nonexistent", "triage")

    def test_delete_task(self, service):
        task = service.create_task(title="Test")
        assert service.delete_task(task.id)
        assert service.state.get_task(task.id) is None

    def test_update_task(self, service):
        task = service.create_task(title="Old")
        updated = service.update_task(task.id, title="New", priority=Priority.AOG)
        assert updated.title == "New"
        assert updated.priority == Priority.AOG

    def test_assign_task(self, service):
        task = service.create_task(title="Test")
        updated = service.assign_task(task.id, "张工")
        assert updated.assignee == "张工"


class TestBoardService:
    """BoardService 测试。"""

    @pytest.fixture
    def service(self):
        # 先创建一些任务
        task_svc = TaskService()
        for i in range(3):
            task_svc.create_task(title=f"Test Task {i}")
        return BoardService()

    def test_get_board(self, service):
        board = service.get_board()
        assert board is not None
        assert len(board.columns) > 0
        assert "backlog" in board.tasks

    def test_search_tasks(self, service):
        # 创建可搜索的任务
        task_svc = TaskService()
        task_svc.create_task(
            title="起落架专项排故",
            ata_chapter="32-41-03",
            aircraft_reg="B-5823",
        )
        task_svc.create_task(title="发动机检查")

        results = service.search_tasks("起落架")
        assert len(results) >= 1
        assert any("起落架" in r.title for r in results)

    def test_search_no_results(self, service):
        results = service.search_tasks("zzz_nonexistent_zzz")
        assert len(results) == 0

    def test_get_stats(self, service):
        stats = service.get_stats()
        assert "total" in stats
        assert isinstance(stats["total"], int)

    def test_fleet_summary(self, service):
        summary = service.get_fleet_summary()
        assert "total" in summary
        assert summary["total"] == 0  # 默认无飞机
