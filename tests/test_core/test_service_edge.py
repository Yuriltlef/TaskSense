"""业务服务层 — 边界与深度测试."""

import pytest
from datetime import datetime, timedelta

from app.core.models.task import Task, TaskStatus, Priority, TaskType
from app.core.services.task_service import TaskService
from app.core.services.board_service import BoardService
from app.core.validators import BusinessRuleError


class TestTaskServiceDeep:
    """TaskService — 深度测试。"""

    @pytest.fixture
    def svc(self):
        return TaskService()

    def test_create_with_all_args(self, svc):
        """使用所有参数创建任务。"""
        now = datetime.now()
        t = svc.create_task(
            title="C检机身检查",
            description="按AMM 53-10-01执行详细检查",
            aircraft_reg="B-5823",
            aircraft_model="737-800",
            ata_chapter="53-10-01",
            priority="cat_b",
            task_type="inspection",
            assignee="张工",
            due_date=now + timedelta(days=7),
            estimated_hours=48.0,
            zone="100",
            fault_code="53-10-01-601",
            created_by="planner",
        )
        assert t.title == "C检机身检查"
        assert t.aircraft_reg == "B-5823"
        assert t.ata_section == "53"  # 自动提取
        assert t.priority == Priority.CAT_B
        assert t.task_type == TaskType.INSPECTION

    def test_create_strips_title(self, svc):
        """标题前后空格被去除。"""
        t = svc.create_task(title="  起落架排故  ")
        assert t.title == "起落架排故"

    def test_create_uppercases_reg(self, svc):
        """注册号自动转大写。"""
        t = svc.create_task(title="Test", aircraft_reg="b-5823")
        assert t.aircraft_reg == "B-5823"

    def test_create_extracts_ata_section(self, svc):
        """ATA section 从 chapter 自动提取。"""
        t = svc.create_task(title="Test", ata_chapter="32-41-03")
        assert t.ata_section == "32"

        t2 = svc.create_task(title="Test", ata_chapter="49")
        assert t2.ata_section == "49"

        t3 = svc.create_task(title="Test", ata_chapter="")
        assert t3.ata_section == ""

    def test_move_full_pipeline(self, svc):
        """完整状态管线：backlog → triage → scheduled → ready →
        in_progress → inspection → completed → archived。"""
        t = svc.create_task(title="Pipeline")
        path = ["triage", "scheduled", "ready", "in_progress",
                "inspection", "completed", "archived"]
        for col in path:
            svc.move_task(t.id, col)
        updated = svc.state.get_task(t.id)
        assert updated.status == TaskStatus.ARCHIVED

    def test_move_with_parts_hold_path(self, svc):
        """经过 Parts Hold 的路径。"""
        t = svc.create_task(title="Test")
        path = ["triage", "scheduled", "ready", "in_progress",
                "parts_hold", "ready", "in_progress", "completed"]
        for col in path:
            svc.move_task(t.id, col)
        updated = svc.state.get_task(t.id)
        assert updated.status == TaskStatus.COMPLETED

    def test_multiple_moves_same_task(self, svc):
        """同任务在不同状态间多次移动。"""
        t = svc.create_task(title="Test")
        # backlog → triage → scheduled → triage（允许回退）
        svc.move_task(t.id, "triage")
        svc.move_task(t.id, "scheduled")
        svc.move_task(t.id, "triage")  # scheduled 允许退回到 triage
        updated = svc.state.get_task(t.id)
        assert updated.status == TaskStatus.TRIAGE

    def test_update_priority(self, svc):
        """单独更新优先级。"""
        t = svc.create_task(title="Test", priority="cat_d")
        assert t.priority == Priority.CAT_D
        updated = svc.update_task(t.id, priority=Priority.AOG)
        assert updated.priority == Priority.AOG

    def test_assign_task_to_none(self, svc):
        """取消分配。"""
        t = svc.create_task(title="Test", assignee="张工")
        svc.assign_task(t.id, "")
        updated = svc.state.get_task(t.id)
        assert updated.assignee == ""

    def test_toggle_checklist_item(self, svc):
        """切换检查清单项状态。"""
        t = svc.create_task(title="Test")
        t.add_checklist_item("Step A")
        t.add_checklist_item("Step B")

        svc.toggle_checklist_item(t.id, t.checklist[0].id, "张工")
        updated = svc.state.get_task(t.id)
        assert updated.checklist[0].completed
        assert updated.checklist[0].completed_by == "张工"

    def test_toggle_nonexistent_item(self, svc):
        """切换不存在的清单项：item_id 不存在返回 None。"""
        t = svc.create_task(title="Test")
        t.add_checklist_item("Real item")
        result = svc.toggle_checklist_item(t.id, "nonexistent", "user")
        assert result is None  # 未找到匹配的清单项

    def test_toggle_nonexistent_task(self, svc):
        """不存在的任务。"""
        result = svc.toggle_checklist_item("nonexistent", "item1", "user")
        assert result is None

    def test_set_priority_invalid_value(self, svc):
        """无效优先级字符串抛异常（需要先有有效任务）。"""
        t = svc.create_task(title="Test")
        with pytest.raises(ValueError):
            svc.set_priority(t.id, "urgent")

    def test_create_task_default_priority(self, svc):
        """默认优先级为 CAT_C。"""
        t = svc.create_task(title="Test")
        assert t.priority == Priority.CAT_C

    def test_create_task_default_type(self, svc):
        """默认任务类型为 TROUBLESHOOT。"""
        t = svc.create_task(title="Test")
        assert t.task_type == TaskType.TROUBLESHOOT


class TestBoardServiceDeep:
    """BoardService — 深度测试。"""

    @pytest.fixture
    def svc(self):
        # 确保有数据
        ts = TaskService()
        ts.create_task(title="AOG起落架", priority="aog",
                       ata_chapter="32-41-03", aircraft_reg="B-5823")
        ts.create_task(title="发动机检查", priority="cat_c",
                       ata_chapter="72-00-01", aircraft_reg="B-2518")
        ts.create_task(title="APU勤务", priority="cat_d",
                       ata_chapter="49-11-01", aircraft_reg="B-5823")
        return BoardService()

    def test_search_by_priority_term(self, svc):
        """搜索优先级关键词。"""
        results = svc.search_tasks("AOG")
        assert len(results) >= 1
        assert any("AOG" in r.title for r in results)

    def test_search_by_ata(self, svc):
        """搜索 ATA 章节。"""
        results = svc.search_tasks("32-41")
        assert len(results) >= 1

    def test_search_by_aircraft(self, svc):
        """按飞机注册号搜索。"""
        results = svc.search_tasks("B-5823")
        assert len(results) >= 2  # 两架 B-5823 的任务

    def test_search_empty_query(self, svc):
        """空搜索返回空。"""
        assert svc.search_tasks("") == []

    def test_search_case_insensitive(self, svc):
        """大小写不敏感。"""
        results1 = svc.search_tasks("aog")
        results2 = svc.search_tasks("AOG")
        assert len(results1) == len(results2)

    def test_filter_and_search_independent(self, svc):
        """筛选和搜索独立工作。"""
        from app.core.models.kanban import FilterState
        svc.set_filters(FilterState(priorities=["aog"]))
        board = svc.get_board()
        # 筛选后看板只包含 AOG 任务
        for col_id, task_ids in board.tasks.items():
            for tid in task_ids:
                task = svc.state.get_task(tid)
                assert task.priority == Priority.AOG

        # 搜索仍独立进行
        results = svc.search_tasks("APU")
        assert len(results) >= 1

    def test_set_swimlane(self, svc):
        """设置 Swimlane 分组。"""
        svc.set_swimlane("ata")
        board = svc.get_board()
        assert board.swimlane_by == "ata"

        svc.set_swimlane(None)
        board = svc.get_board()
        assert board.swimlane_by is None

    def test_reorder_column(self, svc):
        """列排序：验证 reorder 不抛错。"""
        ts = TaskService()
        t1 = ts.create_task(title="Reorder_Test_A")
        t2 = ts.create_task(title="Reorder_Test_B")
        # reorder 应正常执行
        svc.reorder_column("backlog", [t1.id, t2.id])
        board = svc.get_board()
        assert board is not None

    def test_stats_consistency(self, svc):
        """统计与看板状态一致。"""
        stats = svc.get_stats()
        board = svc.get_board()
        total_from_stats = stats["total"]
        total_from_board = sum(len(ids) for ids in board.tasks.values())
        # 注意：筛选可能影响看板可见数
        assert total_from_stats >= total_from_board

    def test_stats_includes_info(self, svc):
        """统计信息包含各列计数。"""
        stats = svc.get_stats()
        for key in ["total", "backlog", "aog_count", "overdue"]:
            assert key in stats, f"Missing key: {key}"


class TestTaskServiceConcurrency:
    """TaskService — 并发场景模拟（单线程）。"""

    def test_rapid_create_and_move(self):
        """快速交替创建和移动。"""
        svc = TaskService()
        before = len(svc.state.get_all_tasks())
        tasks = []
        for i in range(50):
            t = svc.create_task(title=f"Task Rapid {i}")
            tasks.append(t)
            if i % 3 == 0 and tasks:
                try:
                    svc.move_task(tasks[-1].id, "triage")
                except (BusinessRuleError, ValueError):
                    pass

        after = len(svc.state.get_all_tasks())
        assert after - before == 50

    def test_interleaved_operations(self):
        """交叉操作：创建、移动、更新、删除。"""
        svc = TaskService()
        before = len(svc.state.get_all_tasks())
        created = []

        # 创建 20 个
        for i in range(20):
            t = svc.create_task(title=f"Interleave T{i}")
            created.append(t)

        # 移动偶数索引
        for i in range(0, len(created), 2):
            try:
                svc.move_task(created[i].id, "triage")
            except (BusinessRuleError, ValueError):
                pass

        # 更新前 5 个
        for i in range(min(5, len(created))):
            svc.update_task(created[i].id, assignee=f"User{i}")

        # 删除后 3 个
        for i in range(max(0, len(created) - 3), len(created)):
            svc.delete_task(created[i].id)

        after = len(svc.state.get_all_tasks())
        # 创建了 20 个，删除了 3 个 → 净增 17 个
        assert after - before == 17
