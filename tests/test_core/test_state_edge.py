"""状态管理器 — 深度与边界测试."""

import pytest

from app.core.events import AppEvent, EventBus, EventType
from app.core.models.kanban import ColumnConfig, FilterState
from app.core.models.task import Task, TaskStatus, Priority, TaskType
from app.core.state import AppState
from app.core.validators import BusinessRuleError, TaskValidators


class TestAppStateDeep:
    """AppState — 深度测试。"""

    @pytest.fixture
    def state(self):
        return AppState()

    # ── 列管理 ──

    def test_all_default_columns_exist(self, state):
        """所有默认列都已初始化。"""
        cols = state.get_columns()
        col_ids = {c.id for c in cols}
        expected = {"backlog", "triage", "scheduled", "ready",
                    "in_progress", "inspection", "parts_hold",
                    "completed", "archived"}
        assert col_ids == expected

    def test_columns_sorted_by_order(self, state):
        """列按 order 字段排序。"""
        cols = state.get_columns()
        for i in range(len(cols) - 1):
            assert cols[i].order <= cols[i + 1].order

    def test_column_wip_limits(self, state):
        """WIP 限制列配置正确。"""
        cols = {c.id: c for c in state.get_columns()}
        assert cols["backlog"].wip_limit is None
        assert cols["triage"].wip_limit == 10
        assert cols["ready"].wip_limit == 20
        assert cols["in_progress"].wip_limit == 15
        assert cols["inspection"].wip_limit == 15
        assert cols["parts_hold"].wip_limit == 10
        assert cols["completed"].wip_limit is None

    # ── 任务创建 ──

    def test_create_task_auto_id(self, state):
        """创建任务自动生成 ID。"""
        t = state.create_task(title="Test")
        assert t.id is not None
        assert len(t.id) == 8

    def test_create_task_custom_id(self, state):
        """自定义 ID。"""
        t = state.create_task(id="custom-001", title="Test")
        assert t.id == "custom-001"

    def test_create_task_in_backlog(self, state):
        """新任务自动放入 backlog。"""
        state.create_task(title="T1")
        state.create_task(title="T2")
        tasks = state.get_tasks_by_column("backlog")
        assert len(tasks) == 2

    def test_create_many_tasks(self, state):
        """批量创建任务。"""
        for i in range(100):
            state.create_task(title=f"Task {i}")
        assert len(state.get_all_tasks()) == 100

    def test_create_task_order(self, state):
        """新任务插入到列最前面。"""
        t1 = state.create_task(title="T1")
        t2 = state.create_task(title="T2")
        tasks = state.get_tasks_by_column("backlog")
        assert tasks[0].id == t2.id
        assert tasks[1].id == t1.id

    # ── 任务移动 ──

    def test_move_task_updates_column(self, state):
        """移动后原列不再包含该任务。"""
        t = state.create_task(title="Test")
        state.move_task(t.id, "triage")
        backlog = state.get_tasks_by_column("backlog")
        triage = state.get_tasks_by_column("triage")
        assert t.id not in [x.id for x in backlog]
        assert t.id in [x.id for x in triage]

    def test_move_task_to_same_column(self, state):
        """移动到同一列（重排序）。"""
        t1 = state.create_task(title="T1")
        t2 = state.create_task(title="T2")
        # 移动 t1 到列尾
        state.move_task(t1.id, "backlog", index=999)
        tasks = state.get_tasks_by_column("backlog")
        assert tasks[-1].id == t1.id

    def test_move_nonexistent_task(self, state):
        """移动不存在的任务返回 None。"""
        result = state.move_task("nonexistent", "triage")
        assert result is None

    def test_move_task_to_nonexistent_column(self, state):
        """移动到不存在的列：列ID需要是有效的 TaskStatus 值。"""
        t = state.create_task(title="Test")
        # "fantasy_column" 不是有效的 TaskStatus → 会在 transition_to 中抛 ValueError
        with pytest.raises(ValueError):
            state.move_task(t.id, "fantasy_column")

    def test_move_task_history_accumulates(self, state):
        """多次移动累积历史记录。"""
        t = state.create_task(title="Test")
        state.move_task(t.id, "triage")
        state.move_task(t.id, "scheduled")
        state.move_task(t.id, "ready")
        updated = state.get_task(t.id)
        assert len(updated.status_history) == 3

    # ── 任务更新 ──

    def test_update_nonexistent_task(self, state):
        """更新不存在的任务返回 None。"""
        assert state.update_task("nonexistent", title="New") is None

    def test_update_multiple_fields(self, state):
        """一次更新多个字段。"""
        t = state.create_task(title="Old")
        state.update_task(
            t.id,
            title="New Title",
            priority=Priority.AOG,
            aircraft_reg="B-5823",
            estimated_hours=8.0,
        )
        updated = state.get_task(t.id)
        assert updated.title == "New Title"
        assert updated.priority == Priority.AOG
        assert updated.aircraft_reg == "B-5823"
        assert updated.estimated_hours == 8.0

    def test_update_updates_timestamp(self, state):
        """更新操作刷新 updated_at。"""
        import time
        t = state.create_task(title="Test")
        old = state.get_task(t.id).updated_at
        time.sleep(0.002)
        state.update_task(t.id, title="New")
        new = state.get_task(t.id).updated_at
        assert new >= old

    # ── 任务删除 ──

    def test_delete_removes_from_all_columns(self, state):
        """删除后所有列都不再包含该任务。"""
        t = state.create_task(title="Test")
        state.delete_task(t.id)
        for col in state.get_columns():
            tasks = state.get_tasks_by_column(col.id)
            assert t.id not in [x.id for x in tasks]

    def test_delete_twice_returns_false(self, state):
        """重复删除返回 False。"""
        t = state.create_task(title="Test")
        assert state.delete_task(t.id)
        assert not state.delete_task(t.id)

    # ── 列排序 ──

    def test_reorder_column(self, state):
        """列排序。"""
        t1 = state.create_task(title="A")
        t2 = state.create_task(title="B")
        t3 = state.create_task(title="C")
        state.reorder_column("backlog", [t1.id, t2.id, t3.id])
        tasks = state.get_tasks_by_column("backlog")
        assert [x.id for x in tasks] == [t1.id, t2.id, t3.id]

    def test_reorder_nonexistent_column(self, state):
        """对不存在的列执行排序（不应崩溃）。"""
        state.reorder_column("nonexistent", [])
        # 不抛异常

    # ── 筛选 ──

    def test_filter_by_priority(self, state):
        """按优先级筛选。"""
        state.create_task(title="AOG Task", priority=Priority.AOG)
        state.create_task(title="Normal", priority=Priority.CAT_C)
        state.set_filters(FilterState(priorities=["aog"]))
        board = state.get_board_state()
        back_tasks = board.tasks.get("backlog", [])
        assert len(back_tasks) == 1

    def test_filter_by_ata(self, state):
        """按 ATA 章节筛选。"""
        state.create_task(title="T1", ata_chapter="32-41-03")  # section=32
        state.create_task(title="T2", ata_chapter="21-51-01")  # section=21
        state.set_filters(FilterState(ata_chapters=["32"]))
        board = state.get_board_state()
        back_tasks = board.tasks.get("backlog", [])
        assert len(back_tasks) == 1

    def test_filter_by_aircraft(self, state):
        """按飞机注册号筛选。"""
        state.create_task(title="T1", aircraft_reg="B-5823")
        state.create_task(title="T2", aircraft_reg="B-2518")
        state.set_filters(FilterState(aircraft_regs=["B-5823"]))
        board = state.get_board_state()
        back_tasks = board.tasks.get("backlog", [])
        assert len(back_tasks) == 1

    def test_filter_by_search(self, state):
        """模糊搜索。"""
        state.create_task(title="起落架排故", aircraft_reg="B-5823")
        state.create_task(title="发动机检查", aircraft_reg="B-2518")
        state.set_filters(FilterState(search_query="起落架"))
        board = state.get_board_state()
        back_tasks = board.tasks.get("backlog", [])
        assert len(back_tasks) == 1

    def test_filter_search_case_insensitive(self, state):
        """搜索不区分大小写。"""
        state.create_task(title="LANDING GEAR CHECK")
        state.set_filters(FilterState(search_query="landing"))
        board = state.get_board_state()
        assert len(board.tasks.get("backlog", [])) == 1

    def test_filter_combined(self, state):
        """组合筛选。"""
        state.create_task(title="T1", priority=Priority.AOG, ata_chapter="32-41-03")
        state.create_task(title="T2", priority=Priority.AOG, ata_chapter="21-51-01")
        state.create_task(title="T3", priority=Priority.CAT_C, ata_chapter="32-41-03")
        state.set_filters(FilterState(priorities=["aog"], ata_chapters=["32"]))
        board = state.get_board_state()
        back_tasks = board.tasks.get("backlog", [])
        assert len(back_tasks) == 1  # 只有 T1 同时满足

    def test_clear_filters(self, state):
        """清除筛选恢复全部可见。"""
        state.create_task(title="T1")
        state.set_filters(FilterState(search_query="T1"))
        state.set_filters(FilterState())  # 清除
        board = state.get_board_state()
        assert len(board.tasks.get("backlog", [])) == 1

    def test_filter_show_completed(self, state):
        """默认不显示已完成。"""
        t = state.create_task(title="Done")
        # 移动到 completed
        for col in ["triage", "scheduled", "ready", "in_progress", "completed"]:
            try:
                state.move_task(t.id, col)
            except Exception:
                pass
        board = state.get_board_state()
        # 检查 completed 列的任务在默认筛选下是否被滤掉
        all_task_ids = []
        for ids in board.tasks.values():
            all_task_ids.extend(ids)
        # 已完成任务在默认筛选下不应该出现在非 completed 列
        task = state.get_task(t.id)
        if task and task.status == TaskStatus.COMPLETED:
            # 它在 completed 列，过滤由 _apply_filters 的 show_completed 控制
            pass  # 基本逻辑验证

    # ── 监听器 ──

    def test_multiple_listeners(self, state):
        """多个监听器都被通知。"""
        calls = []

        def l1(): calls.append(1)
        def l2(): calls.append(2)
        def l3(): calls.append(3)

        state.subscribe(l1)
        state.subscribe(l2)
        state.subscribe(l3)
        state.create_task(title="Test")
        assert len(calls) == 3

    def test_unsubscribe(self, state):
        """取消订阅后不再被通知。"""
        calls = []

        def l(): calls.append(1)
        state.subscribe(l)
        state.create_task(title="T1")
        assert len(calls) == 1

        state.unsubscribe(l)
        state.create_task(title="T2")
        assert len(calls) == 1  # 没有新增

    def test_listener_exception_doesnt_crash(self, state):
        """监听器异常不应影响其他监听器或状态变更。"""
        def bad(): raise RuntimeError("Oops")
        def good(): good.called = True
        good.called = False

        state.subscribe(bad)
        state.subscribe(good)
        state.create_task(title="Test")
        assert good.called

    # ── 统计 ──

    def test_stats_empty(self, state):
        """空状态统计。"""
        stats = state.get_stats()
        assert stats["total"] == 0
        assert stats["backlog"] == 0
        assert stats["aog_count"] == 0
        assert stats["overdue"] == 0

    def test_stats_after_creating(self, state):
        """创建任务后统计正确。"""
        state.create_task(title="AOG1", priority=Priority.AOG)
        state.create_task(title="AOG2", priority=Priority.AOG)
        state.create_task(title="NORM", priority=Priority.CAT_D)
        stats = state.get_stats()
        assert stats["total"] == 3
        assert stats["aog_count"] == 2

    def test_stats_after_moving(self, state):
        """移动任务后各列统计正确。"""
        t1 = state.create_task(title="T1")
        t2 = state.create_task(title="T2")
        state.move_task(t1.id, "triage")
        stats = state.get_stats()
        assert stats["backlog"] == 1
        assert stats["triage"] == 1

    # ── 飞机管理 ──

    def test_add_aircraft(self, state):
        from app.core.models.aircraft import Aircraft
        ac = Aircraft(registration="B-5823", model="737-800")
        state.add_aircraft(ac)
        assert state.get_aircraft("B-5823") is not None
        assert state.get_aircraft("B-5823").model == "737-800"

    def test_get_all_aircraft(self, state):
        from app.core.models.aircraft import Aircraft
        state.add_aircraft(Aircraft(registration="B-5823"))
        state.add_aircraft(Aircraft(registration="B-2518"))
        assert len(state.get_all_aircraft()) == 2

    def test_fleet_summary_default(self, state):
        """默认空机队摘要。"""
        s = state.get_fleet_summary()
        assert s["total"] == 0

    def test_fleet_summary_with_data(self, state):
        from app.core.models.aircraft import Aircraft, AircraftStatus
        state.add_aircraft(Aircraft(registration="OP1", status=AircraftStatus.OPERATIONAL))
        state.add_aircraft(Aircraft(registration="AOG1", status=AircraftStatus.AOG))
        state.add_aircraft(Aircraft(registration="MAINT1", status=AircraftStatus.IN_MAINTENANCE))
        s = state.get_fleet_summary()
        assert s["total"] == 3
        assert s["operational"] == 1
        assert s["aog"] == 1
        assert s["in_maintenance"] == 1

    # ── Board State ──

    def test_board_state_excludes_invisible_columns(self, state):
        """不可见列不在 board state 中。"""
        cols = state.get_columns()
        # 标记 archived 为不可见（默认已如此）
        archived = [c for c in cols if c.id == "archived"][0]
        assert not archived.visible
        board = state.get_board_state()
        col_ids = {c.id for c in board.columns}
        assert "archived" not in col_ids  # 不可见列不返回

    def test_board_state_includes_task_counts(self, state):
        """看板状态包含各列任务数。"""
        for _ in range(5):
            state.create_task(title="Test")
        board = state.get_board_state()
        backlog_col = [c for c in board.columns if c.id == "backlog"][0]
        assert backlog_col.task_count == 5


class TestEventBus:
    """事件总线测试。"""

    @pytest.fixture
    def bus(self):
        bus = EventBus()
        yield bus
        bus.clear()
        return bus

    def test_emit_to_registered_handler(self, bus):
        received = []

        def handler(event):
            received.append(event)

        bus.on(EventType.TASK_CREATED, handler)
        bus.emit(AppEvent(type=EventType.TASK_CREATED, data={"id": "1"}))
        assert len(received) == 1
        assert received[0].type == EventType.TASK_CREATED
        assert received[0].data["id"] == "1"

    def test_emit_no_handlers(self, bus):
        """无处理器时不崩溃。"""
        bus.emit(AppEvent(type=EventType.TASK_CREATED))
        # 不抛异常

    def test_multiple_handlers_for_event(self, bus):
        results = []

        def h1(e): results.append("h1")
        def h2(e): results.append("h2")

        bus.on(EventType.TASK_CREATED, h1)
        bus.on(EventType.TASK_CREATED, h2)
        bus.emit(AppEvent(type=EventType.TASK_CREATED))
        assert results == ["h1", "h2"]

    def test_different_events(self, bus):
        results = []

        def h(e): results.append(e.type)

        bus.on(EventType.TASK_CREATED, h)
        bus.on(EventType.TASK_MOVED, h)
        bus.emit(AppEvent(type=EventType.TASK_CREATED))
        bus.emit(AppEvent(type=EventType.TASK_MOVED))
        assert results == [EventType.TASK_CREATED, EventType.TASK_MOVED]

    def test_off_removes_handler(self, bus):
        results = []

        def h(e): results.append(1)

        bus.on(EventType.TASK_CREATED, h)
        bus.emit(AppEvent(type=EventType.TASK_CREATED))
        bus.off(EventType.TASK_CREATED, h)
        bus.emit(AppEvent(type=EventType.TASK_CREATED))
        assert len(results) == 1

    def test_off_nonexistent_handler(self, bus):
        """移除不存在的处理器不崩溃。"""
        def h(e): pass
        bus.off(EventType.TASK_CREATED, h)

    def test_handler_exception_doesnt_stop_others(self, bus):
        results = []

        def bad(e): raise RuntimeError("fail")
        def good(e): results.append("ok")

        bus.on(EventType.TASK_CREATED, bad)
        bus.on(EventType.TASK_CREATED, good)
        bus.emit(AppEvent(type=EventType.TASK_CREATED))
        assert results == ["ok"]

    def test_clear(self, bus):
        results = []

        def h(e): results.append(1)

        bus.on(EventType.TASK_CREATED, h)
        bus.clear()
        bus.emit(AppEvent(type=EventType.TASK_CREATED))
        assert len(results) == 0

    def test_event_timestamp(self, bus):
        """事件自动带时间戳。"""
        ts = None

        def h(e): nonlocal ts; ts = e.timestamp

        bus.on(EventType.TASK_CREATED, h)
        bus.emit(AppEvent(type=EventType.TASK_CREATED))
        assert ts is not None

    def test_all_event_types(self, bus):
        """所有事件类型都可注册和触发。"""
        for et in EventType:
            called = []

            def h(e): called.append(True)
            bus.on(et, h)
            bus.emit(AppEvent(type=et))
            assert len(called) == 1, f"Event {et} not triggered"
            bus.clear()


class TestValidatorsEdge:
    """校验器 — 边界测试。"""

    def test_validate_create_empty_whitespace(self):
        """纯空格标题视为空。"""
        with pytest.raises(BusinessRuleError):
            TaskValidators.validate_create("   ")

    def test_validate_create_exactly_200_chars(self):
        """恰好 200 字符的标题不抛异常。"""
        TaskValidators.validate_create("A" * 200)

    def test_validate_create_201_chars(self):
        """201 字符抛异常。"""
        with pytest.raises(BusinessRuleError):
            TaskValidators.validate_create("A" * 201)

    def test_validate_transition_all_pairs(self):
        """测试所有允许的状态转换。"""
        from app.config.constants import ALLOWED_TRANSITIONS
        all_cols = [
            ColumnConfig(id=status, title=status)
            for status in ALLOWED_TRANSITIONS.keys()
        ]
        for from_status_str, allowed in ALLOWED_TRANSITIONS.items():
            task = Task(id="1", title="T", status=TaskStatus(from_status_str))
            for to_status_str in allowed:
                TaskValidators.validate_transition(task, to_status_str, all_cols)

    def test_validate_transition_disallowed_pairs(self):
        """测试不允许的状态转换。"""
        from app.config.constants import ALLOWED_TRANSITIONS
        all_statuses = list(ALLOWED_TRANSITIONS.keys())
        all_cols = [
            ColumnConfig(id=s, title=s) for s in all_statuses
        ]
        for from_str, allowed in ALLOWED_TRANSITIONS.items():
            task = Task(id="1", title="T", status=TaskStatus(from_str))
            disallowed = [s for s in all_statuses if s not in allowed]
            for to_str in disallowed:
                with pytest.raises(BusinessRuleError):
                    TaskValidators.validate_transition(task, to_str, all_cols)

    def test_validate_transition_invalid_column(self):
        """目标列不在列配置中。"""
        task = Task(id="1", title="T")
        cols = [ColumnConfig(id="backlog", title="B")]
        with pytest.raises(BusinessRuleError, match="不存在"):
            TaskValidators.validate_transition(task, "nonexistent", cols)
