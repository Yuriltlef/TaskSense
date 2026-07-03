# -*- coding: utf-8 -*-
"""Agent 服务 — UI 层的 Agent 调用桥梁。含 LLM 离线降级。"""

from app.agent.orchestrator import agent, _load_prompt
from app.core.logging import log
from app.core.state import state


class AgentService:
    """面向 UI 的 Agent 服务封装。"""

    @staticmethod
    def ask(question: str, session_id: str = "default", strict: bool = False,
            cancel_event=None) -> str:
        return agent.ask(question, session_id, strict=strict, cancel_event=cancel_event)

    @staticmethod
    def clear_session(session_id: str = "default"):
        agent.clear_conversation(session_id)

    @staticmethod
    def get_conversation_summary(session_id: str = "default") -> str:
        conv = agent.get_conversation(session_id)
        return conv.get_history_summary()

    @staticmethod
    def get_suggestions(task_description: str) -> dict:
        return agent.suggest_task_template(task_description)

    @staticmethod
    def check_compliance(task_id: str) -> dict:
        return agent.check_compliance(task_id)

    @staticmethod
    def get_daily_report() -> str:
        return agent.generate_daily_report()

    @staticmethod
    def get_board_summary() -> str:
        from app.agent.tools.board_tools import get_board_summary
        return get_board_summary.invoke({})

    @staticmethod
    def search_knowledge(query: str) -> str:
        from app.agent.tools.search_tools import search_knowledge_base
        return search_knowledge_base.invoke({"query": query})

    # ═══════════════════════════════════════════
    # 7 个 Agent 命令（含离线降级）
    # ═══════════════════════════════════════════

    @staticmethod
    def _try_agent(prompt_file: str, user_msg: str, session_id: str,
                   fallback: str = "") -> str:
        """尝试 LLM，不可用则返回 fallback。"""
        from app.agent.llm_client import llm
        if not llm.is_available:
            return fallback
        try:
            prompt = _load_prompt(prompt_file)
            return agent.ask(f"{prompt}\n\n{user_msg}", session_id=session_id)
        except Exception as e:
            log.warn("agent_service.ask", f"LLM failed: {e}")
            return fallback

    @staticmethod
    def generate_outline(user_input: str) -> str:
        desc = user_input.strip()
        # 离线降级：用关键词推断
        ata = agent._guess_ata(desc) if hasattr(agent, '_guess_ata') else ""
        tt = ""
        try:
            suggestion = agent.suggest_task_template(desc)
            ata = suggestion.get("ata_chapter", ata)
            tt = suggestion.get("task_type", tt)
        except Exception:
            pass

        fallback = f"""# 任务大纲: {desc}

**ATA 章节**: {ata or "请指定"}
**任务类型**: {tt or "排故/检查"}
**优先级**: 待确认

## 工作范围
1. 根据「{desc}」执行相关工作
2. 检查相关部件和系统的完整性
3. 记录所有测量值和发现的问题

## 所需工具与航材
- 参考 AMM {ata} 手册
- 标准维护工具

## 操作步骤
1. 准备工作：查阅 AMM {ata}
2. 执行检查/排故
3. 记录结果
4. 恢复飞机至正常状态

## 安全注意事项
- 遵守所有安全程序
- 使用适当的 PPE

## 参考资料
- AMM {ata}
"""
        return AgentService._try_agent("generate_outline.md",
            f"用户需求: {desc}", "outline", fallback)

    @staticmethod
    def generate_tasks(outline: str = "") -> str:
        if not outline:
            # 从看板上下文生成
            tasks = state.get_all_tasks()
            if not tasks:
                return "无可用的任务上下文。请先在 AI 对话中描述需求。"
            titles = [t.title for t in tasks[:5]]
            outline = "现有任务: " + ", ".join(titles)

        # 离线提示
        fallback = (
            "Agent LLM 未配置。请手动创建任务，或配置 API Key 后重试。\n\n"
            "提示：可在设置 → LLM/API 中配置 API Key。"
        )
        return AgentService._try_agent("generate_tasks.md",
            f"上下文: {outline}", "gen_tasks", fallback)

    @staticmethod
    def auto_classify(task_ids: str = "") -> str:
        backlog = [t for t in state.get_all_tasks() if t.status.value == "backlog"]
        if task_ids:
            ids = set(task_ids.split(","))
            backlog = [t for t in backlog if t.id in ids]
        if not backlog:
            return "待处理列中没有任务需要分类。"

        tasks_str = "\n".join(
            f"- [{t.id}] {t.title} (ATA {t.ata_chapter or '未指定'})"
            for t in backlog
        )
        fallback = (
            f"待分类任务 ({len(backlog)} 个):\n{tasks_str}\n\n"
            "Agent LLM 未配置，无法自动分类。"
        )
        return AgentService._try_agent("auto_classify.md",
            f"待处理任务:\n{tasks_str}", "classify", fallback)

    @staticmethod
    def auto_schedule(task_ids: str = "") -> str:
        triage = [t for t in state.get_all_tasks() if t.status.value == "triage"]
        if task_ids:
            ids = set(task_ids.split(","))
            triage = [t for t in triage if t.id in ids]
        if not triage:
            return "已分类列中没有任务需要排程。"

        tasks_str = "\n".join(
            f"- [{t.id}] {t.title} (优先级: {t.priority.value})"
            for t in triage
        )
        fallback = (
            f"待排程任务 ({len(triage)} 个):\n{tasks_str}\n\n"
            "Agent LLM 未配置，无法自动排程。"
        )
        return AgentService._try_agent("auto_schedule.md",
            f"已分类任务:\n{tasks_str}", "schedule", fallback)

    @staticmethod
    def auto_acceptance(task_ids: str = "") -> str:
        insp = [t for t in state.get_all_tasks() if t.status.value == "inspection"]
        if task_ids:
            ids = set(task_ids.split(","))
            insp = [t for t in insp if t.id in ids]
        if not insp:
            return "验收列中没有任务需要审核。"

        tasks_str = "\n".join(
            f"- [{t.id}] {t.title} | 负责人: {t.employee_name or '未指定'} | "
            f"交接日志: {'有' if t.shift_handover_log else '无'}"
            for t in insp
        )
        fallback = (
            f"验收中任务 ({len(insp)} 个):\n{tasks_str}\n\n"
            "Agent LLM 未配置。建议人工逐项检查提交日志完整性。"
        )
        return AgentService._try_agent("auto_acceptance.md",
            f"验收任务:\n{tasks_str}", "acceptance", fallback)

    @staticmethod
    def generate_report(report_type: str = "daily") -> str:
        # 离线基础报表
        from app.core.services.board_service import board_service
        stats = board_service.get_stats()
        fleet = board_service.get_fleet_summary()
        tasks = state.get_all_tasks()
        aog = [t for t in tasks if t.priority.value == "aog"
               and t.status.value not in ("completed", "archived")]
        overdue = [t for t in tasks if t.is_overdue]

        fallback = f"""# 维护{report_type}报表

## 机队状态
- 总计: {fleet.get('total', 0)} 架
- 运行中: {fleet.get('operational', 0)}
- 维修中: {fleet.get('in_maintenance', 0)}
- AOG: {fleet.get('aog', 0)}
- 封存: {fleet.get('stored', 0)}

## 任务概况
- 总任务: {stats.get('total', 0)}
- AOG 紧急: {stats.get('aog_count', 0)}
- 逾期: {stats.get('overdue', 0)}
- 待处理: {stats.get('backlog', 0)}
- 执行中: {stats.get('in_progress', 0)}
- 已完成: {stats.get('completed', 0)}

## 当前 AOG/紧急任务
{chr(10).join(f'- [{t.work_order_id}] {t.title} ({t.aircraft_reg})' for t in aog) if aog else '无'}

## 逾期任务
{chr(10).join(f'- [{t.work_order_id}] {t.title} (逾期 {t.due_date.strftime("%Y-%m-%d") if t.due_date else ""})' for t in overdue) if overdue else '无'}

---
*生成时间: {__import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M")}*
"""
        return AgentService._try_agent("generate_reports.md",
            f"请生成 {report_type} 报告", "report", fallback)

    @staticmethod
    def task_review(task_ids: str = "") -> str:
        # 离线基础审核
        tasks = state.get_all_tasks()
        if task_ids:
            ids = set(task_ids.split(","))
            tasks = [t for t in tasks if t.id in ids]
        else:
            tasks = [t for t in tasks if t.status.value not in ("completed", "archived")]

        issues = []
        for t in tasks:
            if not t.ata_chapter:
                issues.append(f"⚠ [{t.id}] {t.title}: 缺少 ATA 章节")
            if not t.aircraft_reg:
                issues.append(f"⚠ [{t.id}] {t.title}: 缺少飞机注册号")
            if t.is_rii and not t.inspector:
                issues.append(f"🔴 [{t.id}] {t.title}: RII 必检项目未指定检查员")
            if t.estimated_hours and t.estimated_hours > 48:
                issues.append(f"⚠ [{t.id}] {t.title}: 计划工时 {t.estimated_hours}h 超过 48h")

        if not issues:
            summary = "所有任务基本合规。"
        else:
            summary = f"发现 {len(issues)} 个问题:\n" + "\n".join(issues)

        fallback = f"""# 任务合规审核报告

审核时间: {__import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M")}
审核范围: {len(tasks)} 个活跃任务

## 审核结果
{summary}

## 审核维度
- ATA 章节完整性
- 飞机注册号
- RII 必检项
- 工时合理性
"""
        return AgentService._try_agent("task_review.md",
            f"审核 {len(tasks)} 个任务", "review", fallback)
