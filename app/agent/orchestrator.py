"""Agent 编排器 — 协调各子 Agent 与 UI 交互."""

from typing import Optional

from app.agent.tools.board_tools import (
    get_board_summary,
    get_task_detail,
    search_related_tasks,
)
from app.agent.tools.search_tools import (
    search_knowledge_base,
    lookup_ata_chapter,
)
from app.core.state import state


class AgentOrchestrator:
    """Agent 编排器。

    协调各工具函数，提供面向 UI 的简洁接口。
    后续可接入 LangGraph 实现多步推理。

    所有方法返回人类可读的字符串结果。
    """

    def __init__(self):
        self._pipeline = None

    @property
    def pipeline(self):
        if self._pipeline is None:
            from app.knowledge.pipeline import KnowledgePipeline
            self._pipeline = KnowledgePipeline()
        return self._pipeline

    # ── 知识库查询 ──

    def ask(self, question: str) -> str:
        """用户提问 → RAG 检索 + LLM 综合回答 + 引用来源。

        流程：
        1. 从知识库检索相关文档（结构化）
        2. LLM 基于检索结果综合回答，附引用
        3. LLM 不可用时回退
        """
        from app.agent.llm_client import llm as llm_client

        # 1. 结构化 RAG 检索
        kb_results = self.pipeline.search(question, top_k=5)

        # 2. 格式化上下文 + LLM 回答
        if llm_client.is_available and kb_results:
            return self._llm_answer(question, kb_results, llm_client)

        # 3. LLM 不可用 — 纯 RAG 展示
        if kb_results:
            return self._format_rag_results(question, kb_results)

        # 4. 打招呼
        if any(g in question.lower() for g in
               ["你好", "hello", "hi", "hey", "你是谁", "who are you"]):
            if llm_client.is_available:
                return llm_client.chat(
                    "你是 TaskSense 航空维护专家助手。请用中文友好打招呼，简短介绍你可以帮用户做什么。",
                    question)
            return (
                "你好！我是 TaskSense AI 助手。\n\n"
                "我可以帮你:\n"
                "- 检索航空维护知识库（AMM/FIM/AD 等）并推理回答\n"
                "- 解答维护流程和排故步骤\n"
                "- 生成每日维护报告\n"
                "- 检查任务合规性\n\n"
                "请提问具体的航空维护问题。")

        return "未找到相关知识。请尝试提供 ATA 章节号、机型名称或更具体的关键词。"

    def _format_rag_results(self, question: str, results: list[dict]) -> str:
        """纯 RAG 结果格式化（无 LLM）。"""
        lines = [f"搜索: {question}\n"]
        for i, r in enumerate(results, 1):
            meta = r.get("metadata", {})
            src = meta.get("filename", "unknown")
            coll = r.get("collection", "")
            score = r.get("score", 0)
            text = r.get("text", "")[:400]
            tag = f"[{coll}] " if coll else ""
            lines.append(
                f"--- 来源 {i}: {tag}{src} (相关度 {score:.0%}) ---\n{text}...\n")
        return "\n".join(lines)

    def _llm_answer(self, question: str, results: list[dict], llm_client) -> str:
        """LLM 基于 RAG 上下文推理回答，附引用。"""
        # 构建上下文（带编号引用）
        context_parts = []
        for i, r in enumerate(results, 1):
            meta = r.get("metadata", {})
            src = meta.get("filename", "?")
            coll = r.get("collection", "")
            text = r.get("text", "")[:600]
            context_parts.append(f"[{i}] 来源: {src} ({coll})\n{text}")

        context = "\n\n".join(context_parts)

        system = (
            "你是航空维护专家助手。请根据【知识库】回答用户问题。\n\n"
            "要求：\n"
            "1. 简洁回答核心问题（定义/解释/步骤）\n"
            "2. 补充详细说明（如有）\n"
            "3. 正文中用 [1] [2] 标注引用\n"
            "4. 末尾用精确格式列出参考：\n"
            "---REFERENCES---\n"
            "1 | 文件名 | 相关度%\n"
            "2 | 文件名 | 相关度%\n\n"
            "用中文回答。知识库不足时如实说明。"
        )

        scores = "\n".join(
            f"{i+1} | {r.get('metadata',{}).get('filename','?')} | {r.get('score',0):.0%}"
            for i, r in enumerate(results))

        user_msg = (
            f"【知识库检索结果】\n{context}\n\n"
            f"【来源列表（用于 ---REFERENCES---）】\n{scores}\n\n"
            f"【用户问题】\n{question}"
        )

        resp = llm_client.chat(system, user_msg)
        if resp.startswith("[Error]"):
            return self._format_rag_results(question, results)

        return resp

    # ── 任务建议 ──

    def suggest_task_template(self, description: str) -> dict:
        """根据故障描述建议任务模板。

        Returns:
            {ata_chapter, task_type, priority, suggested_steps, references}
        """
        # 检索相关知识
        kb_results = search_knowledge_base.invoke(
            {"query": f"{description} maintenance procedure", "top_k": 3}
        )

        # 查找相似历史任务
        all_tasks = state.get_all_tasks()
        similar = [
            t for t in all_tasks
            if any(w in t.title.lower() for w in description.lower().split()[:3])
        ][:5]

        # 推测 ATA 章节
        ata_chapter = self._guess_ata(description)

        return {
            "ata_chapter": ata_chapter,
            "task_type": "troubleshoot",
            "priority": "cat_c",
            "suggested_steps": self._extract_steps(kb_results),
            "references": [
                {
                    "source": r.get("metadata", {}).get("filename", "unknown"),
                    "snippet": r.get("text", "")[:200],
                    "score": r.get("score", 0),
                }
                for r in [{}]  # placeholder
            ],
            "similar_tasks": [
                {"id": t.id, "title": t.title} for t in similar
            ],
            "raw_kb_result": kb_results,
        }

    # ── 合规检查 ──

    def check_compliance(self, task_id: str) -> dict:
        """检查任务合规性。

        Returns:
            {is_compliant, warnings, suggestions}
        """
        t = state.get_task(task_id)
        if not t:
            return {"is_compliant": False, "warnings": ["任务不存在"]}

        warnings = []
        suggestions = []

        # 检查必要字段
        if not t.ata_chapter:
            warnings.append("缺少 ATA 章节号")

        if not t.aircraft_reg:
            warnings.append("缺少飞机注册号")

        if t.is_rii and not t.inspector:
            warnings.append("RII 必检项目需要指定检查员")

        if t.is_overdue:
            warnings.append(f"任务已逾期（截止: {t.due_date}）")

        # 检查 AD/SB
        if t.ad_numbers:
            # 搜索 AD 相关信息
            for ad in t.ad_numbers:
                kb_hit = search_knowledge_base.invoke(
                    {"query": f"Airworthiness Directive {ad}", "top_k": 1}
                )
                if "未找到" in kb_hit:
                    suggestions.append(f"未在知识库中找到 {ad} 的详细信息")

        return {
            "is_compliant": len(warnings) == 0,
            "warnings": warnings,
            "suggestions": suggestions,
            "task_title": t.title,
        }

    # ── 报告生成 ──

    def generate_daily_report(self) -> str:
        """生成每日维护摘要报告。"""
        from app.core.services.board_service import board_service

        stats = board_service.get_stats()
        fleet = board_service.get_fleet_summary()

        lines = [
            "=" * 40,
            "  航空维护每日报告",
            "=" * 40,
            "",
            "【机队状态】",
            f"  总数: {fleet.get('total', 0)}",
            f"  运行中: {fleet.get('operational', 0)}",
            f"  维修中: {fleet.get('in_maintenance', 0)}",
            f"  AOG: {fleet.get('aog', 0)}",
            "",
            "【任务概况】",
            f"  总任务: {stats.get('total', 0)}",
            f"  AOG 紧急: {stats.get('aog_count', 0)}",
            f"  逾期: {stats.get('overdue', 0)}",
            f"  待处理: {stats.get('backlog', 0)}",
            f"  执行中: {stats.get('in_progress', 0)}",
            f"  已完成: {stats.get('completed', 0)}",
            "",
            "=" * 40,
        ]

        return "\n".join(lines)

    # ── 辅助 ──

    def _guess_ata(self, description: str) -> str:
        """根据描述推测 ATA 章节。"""
        keywords = {
            "起落架": "32", "landing gear": "32",
            "发动机": "72", "engine": "72",
            "燃油": "28", "fuel": "28",
            "空调": "21", "air conditioning": "21",
            "飞行控制": "27", "flight control": "27",
            "APU": "49", "apu": "49",
            "滑油": "79", "oil": "79",
            "电源": "24", "electrical": "24",
            "液压": "29", "hydraulic": "29",
            "机翼": "57", "wing": "57",
            "机身": "53", "fuselage": "53",
            "舱门": "52", "door": "52",
        }
        desc_lower = description.lower()
        for kw, ata in keywords.items():
            if kw.lower() in desc_lower:
                return ata
        return ""

    def _extract_steps(self, kb_result: str) -> list[str]:
        """从知识库结果中提取步骤。"""
        if not kb_result or "未找到" in kb_result:
            return ["参考 AMM 手册相关章节", "执行标准排故流程"]
        return ["根据知识库检索结果执行对应程序"]


# 全局实例
agent = AgentOrchestrator()
