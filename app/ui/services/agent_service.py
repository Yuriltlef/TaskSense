# -*- coding: utf-8 -*-
"""Agent 服务 — UI 层的 Agent 调用桥梁。含 LLM 离线降级。"""

from app.agent.orchestrator import agent, _load_prompt
from app.core.logging import log
from app.core.state import state


class AgentService:
    """面向 UI 的 Agent 服务封装。"""

    @staticmethod
    def ask(question: str, session_id: str = "default", strict: bool = False,
            cancel_event=None, timeout: float = 30.0) -> str:
        return agent.ask(question, session_id, strict=strict,
                         cancel_event=cancel_event, timeout=timeout)

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

    # ═══════════════════════════════════════════
    # 任务提交审核（侧边栏 AI 建议 + 自动验收复用）
    # ═══════════════════════════════════════════

    @staticmethod
    def _build_submission_context(task) -> str:
        """构建任务提交审核上下文。可被 review_submission 和 auto_acceptance 复用。"""
        t = task
        lines = [
            f"任务ID: {t.id}",
            f"工卡号: {t.work_order_id or '无'}",
            f"标题: {t.title}",
            f"描述: {t.description or '无'}",
            f"飞机注册号: {t.aircraft_reg or '未指定'}",
            f"机型: {t.aircraft_model or '未指定'}",
            f"ATA章节: {t.ata_chapter or '未指定'}",
            f"区域: {t.zone or '未指定'}",
            f"优先级: {t.priority.value if hasattr(t.priority, 'value') else str(t.priority)}",
            f"任务类型: {t.task_type.value if hasattr(t.task_type, 'value') else str(t.task_type)}",
            f"负责人: {t.employee_name or t.assignee or '未分配'} (ID: {t.employee_id or '无'})",
            f"预估工时: {t.estimated_hours}h" if t.estimated_hours else "预估工时: 未设置",
            f"实际工时: {t.actual_hours}h" if t.actual_hours else "实际工时: 未填写",
            f"计划时间: {t.planned_start.strftime('%Y-%m-%d %H:%M') if t.planned_start else '未设置'} → {t.planned_end.strftime('%Y-%m-%d %H:%M') if t.planned_end else '未设置'}",
            f"RII必检项目: {'是' if t.is_rii else '否'}",
            f"检查员: {t.inspector or '未指定'}",
            f"阻塞状态: {'是 — ' + t.block_reason if t.is_blocked else '否'}",
            "",
            f"=== 提交材料（交接班日志）===",
            t.shift_handover_log if t.shift_handover_log else "（无提交日志 — 这是严重问题！）",
        ]
        # 检查清单
        done, total = t.checklist_progress()
        if total > 0:
            lines.append("")
            lines.append(f"=== 检查清单 ({done}/{total}) ===")
            for ci in t.checklist:
                status = "✓" if ci.completed else "✗"
                lines.append(f"  [{status}] {ci.text}")
        # 适航指令
        if t.ad_numbers:
            lines.append(f"AD: {', '.join(t.ad_numbers)}")
        if t.sb_numbers:
            lines.append(f"SB: {', '.join(t.sb_numbers)}")
        return "\n".join(lines)

    @staticmethod
    def review_submission(task_id: str) -> str:
        """审核单个任务的提交质量。返回 AI 评审意见（approve/reject/need_more_info + 理由）。

        此方法被侧边栏「AI 建议」按钮调用，也可被 auto_acceptance 工具复用。
        """
        t = state.get_task(task_id)
        if not t:
            return "任务不存在。"

        ctx = AgentService._build_submission_context(t)

        # 离线降级：基本合规检查
        fallback = AgentService._offline_review(t)

        return AgentService._try_agent("review_submission.md",
            f"请审核以下任务提交:\n\n{ctx}", f"review_{task_id}", fallback)

    @staticmethod
    def _offline_review(task) -> str:
        """离线模式下的基本合规检查。"""
        t = task
        issues = []
        if not t.shift_handover_log:
            issues.append("❌ 缺少交接班日志 — 建议驳回")
        if not t.ata_chapter:
            issues.append("⚠ 缺少 ATA 章节")
        if not t.aircraft_reg:
            issues.append("⚠ 缺少飞机注册号")
        if t.is_rii and not t.inspector:
            issues.append("❌ RII 必检项目未指定检查员 — 建议驳回")
        if t.estimated_hours and t.actual_hours:
            if t.actual_hours > t.estimated_hours * 1.5:
                issues.append("⚠ 实际工时远超预估工时，需要说明原因")
        if not t.employee_name and not t.assignee:
            issues.append("⚠ 未指定负责人")

        done, total = t.checklist_progress()
        if total > 0 and done < total:
            issues.append(f"⚠ 检查清单未完成 ({done}/{total})")

        if not issues:
            return ("✅ 建议：**同意**\n\n"
                    "基本审核通过，未发现明显问题。\n\n"
                    "如有疑问请人工复核提交日志细节。")

        return "📋 AI 离线审核结果:\n\n" + "\n".join(issues) + (
            "\n\n💡 建议：配置 LLM API Key 可获得更详细的智能审核意见（包括合规性检查、AD/SB 引用、知识库交叉验证）。"
        )

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
    def task_review(task_ids: str = "", on_batch=None) -> dict:
        """审核活跃任务 — 由 Agent 深度分析 + 本地基础检查兜底。

        优先通过 LLM Agent 调用工具链（get_task_detail / search_knowledge_base
        / search_related_tasks）进行深度审核。LLM 不可用时回退到本地规则检查。
        """
        tasks = state.get_all_tasks()
        if task_ids:
            ids = set(task_ids.split(","))
            tasks = [t for t in tasks if t.id in ids]
        else:
            tasks = [t for t in tasks if t.status.value not in ("completed", "archived")]

        if not tasks:
            log.debug("review_svc", "no tasks to review")
            return {"issues": [], "total_issues": 0, "critical_count": 0,
                    "warning_count": 0, "info_count": 0, "tasks_reviewed": 0}

        log.debug("review_svc", f"reviewing {len(tasks)} tasks")

        # ── Agent 深度审核 → 失败回退本地检查 ──
        log.debug("review_svc", "attempting LLM deep review...")
        try:
            llm_issues = AgentService._llm_task_review(tasks, on_batch=on_batch)
            log.debug("review_svc", f"LLM returned {len(llm_issues)} issues")
            issues = llm_issues
        except Exception as e:
            log.debug("review_svc", f"LLM review FAILED, falling back to local: {e}")
            issues = AgentService._local_task_review(tasks)
        log.debug("review_svc", f"final: {len(issues)} issues")

        severity_order = {"critical": 0, "warning": 1, "info": 2}
        issues.sort(key=lambda i: severity_order.get(i["severity"], 99))

        return {
            "issues": issues,
            "total_issues": len(issues),
            "critical_count": sum(1 for i in issues if i["severity"] == "critical"),
            "warning_count": sum(1 for i in issues if i["severity"] == "warning"),
            "info_count": sum(1 for i in issues if i["severity"] == "info"),
            "tasks_reviewed": len(tasks),
        }

    @staticmethod
    def _local_task_review(tasks: list) -> list[dict]:
        """本地规则检查（快速，LLM 不可用时的兜底）。"""
        issues = []
        for t in tasks:
            tid, title = t.id, t.title
            if not t.ata_chapter:
                issues.append({"task_id": tid, "title": title, "severity": "warning",
                    "dimension": "ATA 章节完整性", "description": "缺少 ATA 章节编号。",
                    "recommendation": "请补充 ATA 章节信息。"})
            if not t.aircraft_reg:
                issues.append({"task_id": tid, "title": title, "severity": "warning",
                    "dimension": "信息完整性", "description": "缺少飞机注册号。",
                    "recommendation": "请关联正确的飞机注册号。"})
            if t.is_rii and not t.inspector:
                issues.append({"task_id": tid, "title": title, "severity": "critical",
                    "dimension": "RII 安全合规", "description": "RII 必检项目未指定检查员。",
                    "recommendation": "请为 RII 项目指定授权检查员。"})
            if t.estimated_hours and t.estimated_hours > 48:
                issues.append({"task_id": tid, "title": title, "severity": "warning",
                    "dimension": "工时合理性", "description": f"计划工时 {t.estimated_hours}h 超过 48h。",
                    "recommendation": "建议拆分为多个子任务。"})
            if t.estimated_hours is not None and t.estimated_hours <= 0:
                issues.append({"task_id": tid, "title": title, "severity": "info",
                    "dimension": "工时合理性", "description": "计划工时未填写。",
                    "recommendation": "请填写预估工时。"})
            if t.status.value == "scheduled":
                if not t.planned_start:
                    issues.append({"task_id": tid, "title": title, "severity": "warning",
                        "dimension": "排程可行性", "description": "缺计划开始时间。",
                        "recommendation": "请设置计划开始和完成时间。"})
                if not t.planned_end:
                    issues.append({"task_id": tid, "title": title, "severity": "warning",
                        "dimension": "排程可行性", "description": "缺计划完成时间。",
                        "recommendation": "请设置计划完成时间。"})
                if not t.employee_id:
                    issues.append({"task_id": tid, "title": title, "severity": "warning",
                        "dimension": "人员匹配", "description": "已排程但未分配人员。",
                        "recommendation": "请分配合适的员工。"})
                if (t.planned_start and t.planned_end
                        and t.planned_start >= t.planned_end):
                    issues.append({"task_id": tid, "title": title, "severity": "critical",
                        "dimension": "排程可行性", "description": "计划开始晚于或等于完成时间。",
                        "recommendation": "请修正时间设置。"})
        # 人员时间冲突
        scheduled = [t for t in tasks if t.status.value == "scheduled"
                     and t.employee_id and t.planned_start and t.planned_end]
        by_emp: dict = {}
        for t in scheduled:
            by_emp.setdefault(t.employee_id, []).append(t)
        for eid, emp_tasks in by_emp.items():
            for i in range(len(emp_tasks)):
                for j in range(i + 1, len(emp_tasks)):
                    ta, tb = emp_tasks[i], emp_tasks[j]
                    if (ta.planned_start < tb.planned_end
                            and tb.planned_start < ta.planned_end):
                        issues.append({
                            "task_id": ta.id, "title": ta.title, "severity": "critical",
                            "dimension": "人员冲突", "description":
                            f"人员 {ta.employee_name or eid} 时间冲突: [{ta.id}] ↔ [{tb.id}]",
                            "recommendation": "调整时间或更换人员。"})
        return issues

    @staticmethod
    def _llm_task_review(tasks: list, on_batch=None) -> list[dict]:
        """分批评审 — 每批 6 个任务，边审边回调渲染。"""
        from app.agent.llm_client import llm
        if not llm.is_available:
            log.debug("review_svc", "LLM not available")
            return []

        CHUNK_SIZE = 6
        total_batches = (len(tasks) + CHUNK_SIZE - 1) // CHUNK_SIZE
        all_issues = []
        import re, json

        for bi in range(0, len(tasks), CHUNK_SIZE):
            chunk = tasks[bi:bi + CHUNK_SIZE]
            batch_num = bi // CHUNK_SIZE + 1
            log.debug("review_svc", f"=== Batch {batch_num}/{total_batches} ({len(chunk)} tasks) ===")

            try:
                batch_issues = AgentService._review_one_batch(
                    chunk, batch_num, total_batches)
                all_issues.extend(batch_issues)
                log.debug("review_svc", f"Batch {batch_num}: {len(batch_issues)} issues, total={len(all_issues)}")
            except Exception as e:
                log.debug("review_svc", f"Batch {batch_num} FAILED: {e}")
                # 为失败批次的每个任务生成错误卡片
                for t in chunk:
                    all_issues.append({
                        "task_id": t.id, "title": t.title, "severity": "critical",
                        "dimension": "系统错误",
                        "description": f"Agent 审核失败（第{batch_num}批）。",
                        "recommendation": f"错误: {str(e)[:150]}",
                    })

            if on_batch:
                on_batch(list(all_issues), batch_num, total_batches)

        return all_issues

    @staticmethod
    def _review_one_batch(tasks: list, batch_num: int, total_batches: int) -> list[dict]:
        """审核单批任务 — 单阶段：调工具收集数据 + 输出 JSON 一步完成。"""
        from app.agent.orchestrator import agent, _load_prompt
        import re, json

        tasks_str = "\n".join(
            f"- [{t.id}] {t.title} | ATA:{t.ata_chapter or '无'} | "
            f"飞机:{t.aircraft_reg or '无'} | 优先级:{t.priority.value} | "
            f"状态:{t.status.value} | 人员:{t.employee_name or '无'} | "
            f"工时:{t.estimated_hours or '无'}h"
            for t in tasks
        )

        prompt = (
            f"{_load_prompt('task_review.md')}\n\n"
            f"## 审核第 {batch_num}/{total_batches} 批（{len(tasks)} 个任务）\n\n"
            f"{tasks_str}\n\n"
            f"## 工作流程\n"
            f"1. 先用 get_task_detail 抽查本批中状态特殊的任务（inspection/scheduled 优先）\n"
            f"2. 收集足够信息后，立即输出 JSON 审核结果\n\n"
            f"## 输出格式\n"
            f"输出一个 JSON 数组（```json 代码块包裹）：\n"
            f'```json\n[\n'
            f'  {{"task_id":"...","title":"...","severity":"critical|warning|info",'
            f'"dimension":"ATA准确性|信息完整性|法规合规|排程可行性|人员匹配|安全",'
            f'"description":"具体问题描述","recommendation":"修复建议"}}\n'
            f']\n```\n\n'
            f"## 审核维度\n"
            f"- ATA 章节 / 必填字段 / RII 检查员 / 工时合理性 / 人员时间冲突\n"
            f"- 每个任务至少检查以上维度，发现问题才输出条目\n"
            f"- 本批 {len(tasks)} 个任务，输出不要超过 {len(tasks) * 3} 个问题\n\n"
            f"现在开始审核并输出 JSON。"
        )

        session_id = f"review_b{batch_num}"
        agent.clear_conversation(session_id)
        result = agent.ask(prompt, session_id=session_id)
        log.debug("review_svc", f"Batch {batch_num} response: {len(result)} chars, "
              f"preview: {result[:200]}")

        # 解析 JSON（多种策略按顺序尝试）
        if len(result.strip()) < 30:
            raise RuntimeError(f"返回过短 ({len(result)} 字符): {result.strip()[:100]}")

        if result.startswith("[Error]"):
            raise RuntimeError(f"LLM 调用失败: {result}")

        # 策略 1: ```json ... ``` 代码块
        json_match = re.search(r'```json\s*\n(.*?)\n\s*```', result, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass  # 继续尝试其他策略

        # 策略 2: 裸 JSON 数组（贪婪匹配到最后一个 ]）
        bare_match = re.search(r'\[\s*\{[\s\S]*\}\s*\]', result)
        if bare_match:
            try:
                return json.loads(bare_match.group(0))
            except json.JSONDecodeError:
                pass

        # 策略 3: 如果整个响应就是 JSON
        stripped = result.strip()
        if stripped.startswith('['):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                pass

        # 策略 4: 逐行提取 JSON 对象（最宽松）
        obj_matches = re.findall(r'\{\s*"task_id"[\s\S]*?\}', result)
        if obj_matches:
            issues = []
            for om in obj_matches:
                try:
                    issues.append(json.loads(om))
                except json.JSONDecodeError:
                    continue
            if issues:
                return issues

        raise RuntimeError(
            f"未找到有效 JSON（{len(result)} 字符）。\n"
            f"响应预览: {result[:300]}\n"
            f"响应尾: ...{result[-200:] if len(result) > 200 else ''}")

    # ═══════════════════════════════════════════
    # 右键菜单 AI 功能
    # ═══════════════════════════════════════════

    @staticmethod
    def _run_single_task_ai(prompt_file: str, session_prefix: str,
                            task_info: dict, cancel_event=None) -> str:
        """所有右键菜单 AI 工具的统一入口。"""
        from app.agent.llm_client import llm
        if not llm.is_available:
            return "[Error] LLM 不可用"
        try:
            prompt = _load_prompt(prompt_file)
            user_msg = "\n".join(f"- {k}: {v}" for k, v in task_info.items())
            full = f"{prompt}\n\n## Task Details\n{user_msg}"
            return agent.ask(full, session_id=f"{session_prefix}_{task_info.get('id','')}",
                           strict=False, cancel_event=cancel_event, timeout=15.0)
        except Exception as e:
            return f"[Error] {e}"

    @staticmethod
    def explain_task(task_info: dict, cancel_event=None) -> str:
        return AgentService._run_single_task_ai(
            "explain_task.md", "explain", task_info, cancel_event)

    @staticmethod
    def search_docs(task_info: dict, cancel_event=None) -> str:
        return AgentService._run_single_task_ai(
            "search_docs.md", "search", task_info, cancel_event)

    @staticmethod
    def classify_single(task_info: dict, cancel_event=None) -> str:
        return AgentService._run_single_task_ai(
            "classify_single.md", "classify", task_info, cancel_event)

    @staticmethod
    def schedule_single(task_info: dict, cancel_event=None) -> str:
        return AgentService._run_single_task_ai(
            "schedule_single.md", "schedule", task_info, cancel_event)

    @staticmethod
    def review_single(task_info: dict, cancel_event=None) -> str:
        return AgentService._run_single_task_ai(
            "review_single.md", "review", task_info, cancel_event)
