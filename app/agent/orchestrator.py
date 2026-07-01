"""Agent 编排器 — 工具调用 + 多轮对话."""

import re
from pathlib import Path
from typing import Optional

from app.agent.conversation import Conversation
from app.core.state import state


# ── 提示词加载 ──

def _load_prompt(name: str) -> str:
    """加载 app/agent/prompts/ 下的 .md 提示词文件。"""
    path = Path(__file__).parent / "prompts" / name
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _build_system_prompt(strict: bool = False) -> str:
    """组装完整系统提示词。"""
    parts = [_load_prompt("system.md")]
    parts.append(_load_prompt("tool_use.md"))
    if strict:
        strict_prompt = _load_prompt("strict_mode.md")
        if strict_prompt:
            parts.append(strict_prompt)
    else:
        normal_prompt = _load_prompt("normal_mode.md")
        if normal_prompt:
            parts.append(normal_prompt)
    return "\n\n".join(p for p in parts if p)


# ── 工具执行器 ──

class ToolExecutor:
    """执行 LLM 请求的工具调用，返回结果文本。"""

    @staticmethod
    def execute(tool_name: str, params: dict) -> str:
        tool_name = tool_name.strip().lower()
        try:
            if tool_name == "search_knowledge_base":
                return ToolExecutor._search_kb(params)
            elif tool_name == "lookup_ata_chapter":
                return ToolExecutor._lookup_ata(params)
            elif tool_name == "get_board_summary":
                from app.agent.tools.board_tools import get_board_summary
                return get_board_summary.invoke({})
            elif tool_name == "get_task_detail":
                from app.agent.tools.board_tools import get_task_detail
                return get_task_detail.invoke(params)
            elif tool_name == "search_related_tasks":
                from app.agent.tools.board_tools import search_related_tasks
                return search_related_tasks.invoke(params)
            else:
                return f"[Error] Unknown tool: {tool_name}"
        except Exception as e:
            return f"[Error] Tool execution failed: {e}"

    @staticmethod
    def _search_kb(params: dict) -> str:
        from app.agent.tools.search_tools import get_pipeline
        pipeline = get_pipeline()
        query = params.get("query", "")
        top_k = int(params.get("top_k", 5))
        doc_type = params.get("doc_type", "")

        stats = pipeline.get_stats()
        total_chunks = stats.get("total", 0)
        if total_chunks == 0:
            return "Knowledge base is empty."

        results = pipeline.search(
            query, top_k=top_k,
            doc_type=doc_type if doc_type else None,
        )
        if not results:
            return f"No results found for '{query}'."

        lines = [f"Search '{query}' — {len(results)} results:"]
        for i, r in enumerate(results, 1):
            meta = r.get("metadata", {})
            src = meta.get("filename", "?")
            ata = meta.get("ata_chapter", "")
            ch = meta.get("chapter")
            pg = meta.get("page_start", "")
            score = r.get("score", 0)
            text = r.get("text", "")[:400]

            loc = ""
            if ch is not None:
                loc += f" Ch.{ch}"
            if ata:
                loc += f" ATA {ata}"
            if pg:
                loc += f" p.{pg}"
            lines.append(
                f"\n[{i}] {src}{loc} (relevance {score:.0%})\n{text}..."
            )
        return "\n".join(lines)

    @staticmethod
    def _lookup_ata(params: dict) -> str:
        from app.agent.tools.search_tools import get_pipeline
        pipeline = get_pipeline()
        ata_code = params.get("ata_code", "")

        stats = pipeline.get_stats()
        total_chunks = stats.get("total", 0)
        if total_chunks == 0:
            return "Knowledge base is empty."

        results = pipeline.search(
            f"ATA {ata_code} maintenance procedures",
            top_k=5,
            ata_filter=ata_code.split("-")[0] if "-" in ata_code else ata_code,
        )
        if not results:
            return f"No results found for ATA {ata_code}."

        lines = [f"ATA {ata_code} — {len(results)} results:"]
        for i, r in enumerate(results, 1):
            text = r.get("text", "")[:300]
            lines.append(f"\n--- {i} (relevance {r.get('score', 0):.0%}) ---\n{text}...")
        return "\n".join(lines)


# ── 工具调用解析 ──

_TOOL_CALL_RE = re.compile(
    r"```tool\s*\n(.*?)```", re.DOTALL | re.IGNORECASE
)


def _parse_tool_calls(text: str) -> list[tuple[str, dict]]:
    """从 LLM 输出中解析工具调用块。

    Returns:
        [(tool_name, {param: value}), ...]
    """
    calls = []
    for block in _TOOL_CALL_RE.findall(text):
        lines = block.strip().split("\n")
        tool_name = ""
        params = {}
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                params[k.strip()] = v.strip()
            elif not tool_name:
                tool_name = line
        if tool_name:
            calls.append((tool_name, params))
    return calls


# ── 编排器 ──

class AgentOrchestrator:
    """Agent 编排器 — 工具调用 + 多轮对话。

    每个 ask() 调用都是一个可能包含多步工具调用的推理过程：
    1. LLM 决定是否需要调用工具
    2. 如需 → 执行工具 → 将结果反馈给 LLM
    3. LLM 基于工具结果生成最终回答
    4. 始终保持对话上下文
    """

    MAX_TOOL_ROUNDS = 3  # 单次 ask() 最多工具调用轮数

    def __init__(self):
        self._pipeline = None
        self._conversations: dict[str, Conversation] = {}
        self._system_prompt = ""

    @property
    def pipeline(self):
        if self._pipeline is None:
            from app.knowledge.pipeline import KnowledgePipeline
            self._pipeline = KnowledgePipeline()
        return self._pipeline

    def _get_system_prompt(self, strict: bool = False) -> str:
        # strict mode changes the prompt, so cache separately
        cache_key = f"strict_{strict}"
        if not hasattr(self, '_prompt_cache'):
            self._prompt_cache = {}
        if cache_key not in self._prompt_cache:
            self._prompt_cache[cache_key] = _build_system_prompt(strict=strict)
        return self._prompt_cache[cache_key]

    # ── 会话管理 ──

    def get_conversation(self, session_id: str = "default",
                         strict: bool = False) -> Conversation:
        if session_id not in self._conversations:
            conv = Conversation(session_id)
            conv.system_prompt = self._get_system_prompt(strict=strict)
            self._conversations[session_id] = conv
        else:
            # 模式切换时更新 system prompt
            conv = self._conversations[session_id]
            new_prompt = self._get_system_prompt(strict=strict)
            if conv.system_prompt != new_prompt:
                conv.system_prompt = new_prompt
        return self._conversations[session_id]

    def clear_conversation(self, session_id: str = "default"):
        if session_id in self._conversations:
            self._conversations[session_id].clear()

    # ── 主入口 ──

    def ask(self, question: str, session_id: str = "default",
            strict: bool = False, cancel_event=None) -> str:
        """用户提问 → Agent 推理（可能含工具调用）→ 回答。"""
        conv = self.get_conversation(session_id, strict=strict)

        from app.agent.llm_client import llm as llm_client

        if not llm_client.is_available:
            return self._offline_search(question)

        conv.add_user(question)

        try:
            response = self._agent_loop(conv, llm_client, cancel_event)
        except Exception as e:
            response = f"[Error] Agent reasoning failed: {e}"

        # 中断消息不记入历史
        if response != "回答已中断":
            conv.add_assistant(response)
        return response

    def _agent_loop(self, conv: Conversation, llm_client,
                    cancel_event=None) -> str:
        """Agent 推理循环：LLM ↔ 工具调用。"""
        # 快速检查取消标志
        if cancel_event and cancel_event.is_set():
            return "回答已中断"

        messages = conv.build_messages()

        for round_num in range(self.MAX_TOOL_ROUNDS + 1):
            if cancel_event and cancel_event.is_set():
                return "回答已中断"

            resp_text = llm_client.chat_messages(messages)

            if resp_text.startswith("[Error]"):
                if round_num == 0:
                    return self._offline_search(conv.last_user_message or "")
                return resp_text

            # 检查是否有工具调用
            tool_calls = _parse_tool_calls(resp_text)
            if not tool_calls:
                # LLM 直接回答 — 返回结果
                return resp_text

            if round_num >= self.MAX_TOOL_ROUNDS:
                if cancel_event and cancel_event.is_set():
                    return "回答已中断"
                messages.append({"role": "assistant", "content": resp_text})
                messages.append({
                    "role": "user",
                    "content": "Please provide your final answer now based on the tool results above. "
                               "Do NOT request more tool calls."
                })
                final = llm_client.chat_messages(messages)
                return final if not final.startswith("[Error]") else resp_text

            # 执行工具调用（执行前检查取消）
            if cancel_event and cancel_event.is_set():
                return "回答已中断"
            tool_results = []
            for tool_name, params in tool_calls:
                if cancel_event and cancel_event.is_set():
                    tool_results.append((tool_name, "回答已中断"))
                    break
                result = ToolExecutor.execute(tool_name, params)
                tool_results.append((tool_name, result))

            # 将工具调用和结果添加到 messages
            messages.append({"role": "assistant", "content": resp_text})
            for tool_name, result in tool_results:
                messages.append({
                    "role": "user",
                    "content": f"[Tool Result: {tool_name}]\n{result}\n\n"
                               f"Continue your response based on the tool results. "
                               f"If you need more information, request another tool call. "
                               f"If you have enough information, provide your final answer."
                })

        # 不应到达这里，但作为兜底
        return llm_client.chat_messages(messages)

    # ── 离线模式 ──

    def _offline_search(self, question: str) -> str:
        """LLM 不可用时 — 纯 RAG 检索。"""
        kb_results = self.pipeline.search(question, top_k=5)
        if not kb_results:
            return (
                "I'm currently offline and couldn't find relevant information "
                "in the knowledge base. Please try again when connected, or "
                "rephrase your question with more specific terms (ATA chapter, "
                "aircraft model, etc.)."
            )
        return self._format_rag_results(question, kb_results)

    def _format_rag_results(self, question: str, results: list[dict]) -> str:
        """纯 RAG 结果格式化。"""
        lines = [f"**Search**: {question}\n"]
        for i, r in enumerate(results, 1):
            meta = r.get("metadata", {})
            src = meta.get("filename", "unknown")
            score = r.get("score", 0)
            text = r.get("text", "")[:800]
            ch = meta.get("chapter")
            pg = meta.get("page_start", "")
            loc = ""
            if ch is not None:
                loc += f" Ch.{ch}"
            if pg:
                loc += f" p.{pg}"
            lines.append(f"--- Source {i}: {src}{loc} ({score:.0%}) ---\n{text}...\n")
        return "\n".join(lines)

    # ── 遗留接口（向后兼容） ──

    def generate_daily_report(self) -> str:
        from app.core.services.board_service import board_service
        stats = board_service.get_stats()
        fleet = board_service.get_fleet_summary()

        return "\n".join([
            "=" * 40,
            "  航空维护每日报告",
            "=" * 40, "",
            "【机队状态】",
            f"  总数: {fleet.get('total', 0)}",
            f"  运行中: {fleet.get('operational', 0)}",
            f"  维修中: {fleet.get('in_maintenance', 0)}",
            f"  AOG: {fleet.get('aog', 0)}", "",
            "【任务概况】",
            f"  总任务: {stats.get('total', 0)}",
            f"  AOG 紧急: {stats.get('aog_count', 0)}",
            f"  逾期: {stats.get('overdue', 0)}",
            f"  待处理: {stats.get('backlog', 0)}",
            f"  执行中: {stats.get('in_progress', 0)}",
            f"  已完成: {stats.get('completed', 0)}", "",
            "=" * 40,
        ])

    def suggest_task_template(self, description: str) -> dict:
        kb_results = self.pipeline.search(f"{description} maintenance procedure", top_k=3)
        all_tasks = state.get_all_tasks()
        similar = [
            t for t in all_tasks
            if any(w in t.title.lower() for w in description.lower().split()[:3])
        ][:5]
        ata_chapter = self._guess_ata(description)

        return {
            "ata_chapter": ata_chapter,
            "task_type": "troubleshoot",
            "priority": "cat_c",
            "suggested_steps": self._extract_steps(
                "\n".join(r.get("text", "")[:200] for r in kb_results)
            ),
            "similar_tasks": [{"id": t.id, "title": t.title} for t in similar],
        }

    def check_compliance(self, task_id: str) -> dict:
        t = state.get_task(task_id)
        if not t:
            return {"is_compliant": False, "warnings": ["Task not found"]}
        warnings = []
        if not t.ata_chapter:
            warnings.append("Missing ATA chapter")
        if not t.aircraft_reg:
            warnings.append("Missing aircraft registration")
        if t.is_rii and not t.inspector:
            warnings.append("RII item requires inspector")
        if t.is_overdue:
            warnings.append(f"Task overdue (deadline: {t.due_date})")
        return {
            "is_compliant": len(warnings) == 0,
            "warnings": warnings,
            "suggestions": [],
            "task_title": t.title,
        }

    @staticmethod
    def _guess_ata(description: str) -> str:
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

    @staticmethod
    def _extract_steps(kb_result: str) -> list[str]:
        if not kb_result:
            return ["Refer to AMM manual", "Execute standard troubleshooting"]
        return ["Follow procedures from knowledge base results"]


# 全局实例
agent = AgentOrchestrator()
