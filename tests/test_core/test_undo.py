"""撤销/重做 功能测试."""

import pytest

from app.core.state import state
from app.core.services.undo_manager import undo_manager
from app.core.services.task_service import task_service
from app.core.models.task import TaskStatus


class TestUndoManager:
    """UndoManager 单元测试。"""

    def test_push_and_undo(self):
        undo_manager.clear()
        results = []

        undo_manager.push("测试操作",
                          undo_fn=lambda: results.append("undo"),
                          redo_fn=lambda: results.append("redo"))
        assert undo_manager.can_undo
        assert not undo_manager.can_redo
        assert undo_manager.undo()
        assert results == ["undo"]
        assert not undo_manager.can_undo
        assert undo_manager.can_redo

    def test_redo(self):
        undo_manager.clear()
        results = []

        undo_manager.push("测试",
                          undo_fn=lambda: results.append("u"),
                          redo_fn=lambda: results.append("r"))
        undo_manager.undo()
        assert undo_manager.redo()
        assert results == ["u", "r"]
        assert undo_manager.can_undo

    def test_new_action_clears_redo(self):
        undo_manager.clear()
        undo_manager.push("op1", lambda: None, lambda: None)
        undo_manager.undo()
        assert undo_manager.can_redo
        undo_manager.push("op2", lambda: None, lambda: None)
        assert not undo_manager.can_redo  # 新操作清空 redo

    def test_max_stack(self):
        undo_manager.clear()
        for i in range(250):
            undo_manager.push(f"op{i}", lambda: None, lambda: None)
        assert undo_manager.can_undo
        # 应该被截断到 MAX_STACK
        undo_manager.undo()
        # 不应该崩溃

    def test_group(self):
        undo_manager.clear()
        results = []

        undo_manager.begin_group("批量操作")
        undo_manager.push("子1", lambda: results.append("u1"), lambda: results.append("r1"))
        undo_manager.push("子2", lambda: results.append("u2"), lambda: results.append("r2"))
        undo_manager.end_group()

        assert undo_manager.can_undo
        assert undo_manager.undo()
        assert results == ["u2", "u1"]  # 逆序撤销

    def test_empty_undo_redo(self):
        undo_manager.clear()
        assert not undo_manager.undo()
        assert not undo_manager.redo()
        assert undo_manager.undo_description == ""
        assert undo_manager.redo_description == ""


class TestStateUndo:
    """State 操作撤销测试。"""

    def setup_method(self):
        undo_manager.clear()
        # 确保 state 干净
        for t in list(state.get_all_tasks()):
            state.delete_task(t.id)

    def test_move_undo_redo(self):
        """移动任务 → 撤销 → 重做。"""
        t = task_service.create_task(title="测试撤销移动", priority="cat_c",
                                     task_type="repair")
        tid = t.id
        task_service.move_task(tid, "triage")
        assert state.get_task(tid).status == TaskStatus.TRIAGE

        # 撤销
        assert undo_manager.can_undo
        assert undo_manager.undo()
        assert state.get_task(tid).status == TaskStatus.BACKLOG

        # 重做
        assert undo_manager.can_redo
        assert undo_manager.redo()
        assert state.get_task(tid).status == TaskStatus.TRIAGE

    def test_update_undo_redo(self):
        """编辑字段 → 撤销 → 重做。"""
        t = task_service.create_task(title="原始标题", priority="cat_c",
                                     task_type="repair")
        tid = t.id

        state.update_task(tid, title="修改后的标题", assignee="Test")
        assert state.get_task(tid).title == "修改后的标题"
        assert state.get_task(tid).assignee == "Test"

        assert undo_manager.undo()
        assert state.get_task(tid).title == "原始标题"
        assert state.get_task(tid).assignee is None

        assert undo_manager.redo()
        assert state.get_task(tid).title == "修改后的标题"
        assert state.get_task(tid).assignee == "Test"

    def test_create_undo(self):
        """创建任务 → 撤销删除。"""
        t = task_service.create_task(title="可撤销创建", priority="cat_c",
                                     task_type="repair")
        tid = t.id
        assert state.get_task(tid) is not None

        assert undo_manager.undo()
        assert state.get_task(tid) is None  # 撤销创建 → 任务被删除

    def test_delete_undo_redo(self):
        """删除任务 → 撤销恢复 → 重做删除。"""
        t = task_service.create_task(title="可恢复删除", priority="cat_c",
                                     task_type="repair")
        tid = t.id
        snapshot_title = t.title

        state.delete_task(tid)
        assert state.get_task(tid) is None

        assert undo_manager.undo()
        restored = state.get_task(tid)
        assert restored is not None
        assert restored.title == snapshot_title

        assert undo_manager.redo()
        assert state.get_task(tid) is None

    def test_replay_guard(self):
        """撤销/重做不会产生新的撤销记录。"""
        t = task_service.create_task(title="测试回放保护", priority="cat_c",
                                     task_type="repair")
        tid = t.id
        state.update_task(tid, title="改一次")
        count_before = len(undo_manager._undo_stack)

        undo_manager.undo()  # 撤销更新
        count_after = len(undo_manager._undo_stack)
        # 撤销后栈应该减少（pop 了更新记录），不会因为 undo 的回调而产生新记录
        assert count_after < count_before
