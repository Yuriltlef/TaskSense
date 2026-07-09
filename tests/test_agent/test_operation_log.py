"""Agent search_operation_log 工具测试."""

import pytest

from app.core.models.log_entry import LogType
from app.core.services.log_service import log_service


def _invoke(query: str, limit: int = 20) -> str:
    from app.agent.tools.search_tools import search_operation_log
    return search_operation_log.invoke({"query": query, "limit": limit})


class TestSearchOperationLog:
    """search_operation_log 工具单元测试。"""

    @pytest.fixture(autouse=True)
    def setup_logs(self):
        """每个测试前清空并填充操作日志。"""
        log_service.clear()
        log_service.log(
            LogType.CREATE_TASK, task_id="task_001",
            task_title="起落架排故",
            user="user",
            description="创建任务: 起落架排故",
            details={"aircraft_reg": "B-5823", "ata_chapter": "32-41-03"},
        )
        log_service.log(
            LogType.KANBAN_MOVE, task_id="task_001",
            task_title="起落架排故",
            user="user",
            description="移动: backlog → triage",
            details={"from_col": "backlog", "to_col": "triage"},
        )
        log_service.log(
            LogType.ACCEPT_TASK, task_id="task_002",
            task_title="发动机孔探检查",
            user="Zhang",
            description="接单: 发动机孔探检查",
            details={"employee_id": "ZH001", "employee_name": "Zhang"},
        )
        log_service.log(
            LogType.SUBMISSION, task_id="task_002",
            task_title="发动机孔探检查",
            user="Zhang",
            description="提交验收: 发动机孔探检查",
            details={"actual_hours": 4.5, "handover_log": "已完成孔探，无异常"},
        )
        log_service.log(
            LogType.BLOCK, task_id="task_003",
            task_title="APU 滑油更换",
            user="Li",
            description="阻塞任务: 等待航材",
            details={"reason": "航材未到货", "from_status": "in_progress"},
        )
        yield
        log_service.clear()

    # ── 基本功能 ──

    def test_find_by_task_title(self):
        """按任务标题关键词搜索。"""
        result = _invoke("起落架")
        assert "起落架排故" in result
        assert "backlog → triage" in result

    def test_find_by_employee(self):
        """按员工姓名搜索——姓名在 detail 中。"""
        result = _invoke("Zhang")
        assert "发动机孔探" in result

    def test_find_by_action_type(self):
        """按操作描述搜索。"""
        result = _invoke("接单")
        assert "孔探" in result

    def test_find_by_detail(self):
        """按详情字段搜索（飞机注册号在 detail 中）。"""
        result = _invoke("B-5823")
        assert "起落架排故" in result

    def test_find_by_handover(self):
        """按交接班日志内容搜索。"""
        result = _invoke("孔探")
        assert "发动机" in result

    # ── 边界条件 ──

    def test_no_match_returns_message(self):
        """无匹配时返回提示信息。"""
        result = _invoke("zzz_nonexistent_zzz")
        assert "未找到" in result

    def test_empty_query_searches_all(self):
        """空查询返回最近日志。"""
        result = _invoke("")
        assert "起落架排故" in result or "操作日志" in result

    def test_partial_match(self):
        """关键词在任务标题中匹配。"""
        result = _invoke("滑油")
        assert "APU" in result

    def test_limit(self):
        """限制返回条数。"""
        result = _invoke("", limit=2)
        lines = result.split("\n")
        item_lines = [l for l in lines if l.strip().startswith(("1.", "2.", "3."))]
        assert len(item_lines) <= 2

    # ── 与 log_service 一致性 ──

    def test_new_log_immediately_searchable(self):
        """日志写入后立即可搜索。"""
        log_service.log(
            LogType.EDIT_TASK, task_id="task_004",
            task_title="新增测试任务",
            user="test",
            description="更新字段: priority, assignee",
        )
        result = _invoke("新增测试")
        assert "新增测试任务" in result


class TestOperationLogEdgeCases:
    """search_operation_log 边界测试。"""

    def test_empty_logs(self):
        """日志为空时返回提示。"""
        log_service.clear()
        result = _invoke("anything")
        assert "未找到" in result
        log_service.clear()

    def test_special_characters(self):
        """特殊字符查询不崩溃。"""
        log_service.clear()
        log_service.log(
            LogType.CREATE_TASK, task_id="t1",
            task_title="测试",
            description="测试任务 @#$%^&*()",
        )
        result = _invoke("@#$%")
        assert isinstance(result, str)
        assert len(result) > 0
        log_service.clear()

    def test_unicode_query(self):
        """中文查询正确匹配。"""
        log_service.clear()
        log_service.log(
            LogType.CREATE_TASK, task_id="t1",
            task_title="发动机主轴承更换",
            description="发动机主轴承更换 — 拆装检查",
        )
        result = _invoke("轴承")
        assert "发动机" in result
        log_service.clear()
