"""会话管理器 — 多轮对话上下文 & 消息历史."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Message:
    """单条消息。"""
    role: str           # "user" | "assistant" | "system" | "tool"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


class Conversation:
    """多轮对话会话。

    - 维护消息历史
    - 自动裁剪旧消息（保留最近 N 轮 + system prompt）
    - 为 LLM API 提供 messages 格式
    """

    MAX_HISTORY_TURNS = 10   # 保留最近 10 轮（20 条 user+assistant）
    MAX_CONTEXT_CHARS = 8000  # 上下文字符上限（裁剪依据）

    def __init__(self, session_id: str = "default"):
        self.session_id = session_id
        self._messages: list[Message] = []
        self._system_prompt: str = ""
        self.created_at = datetime.now()

    # ── 消息操作 ──

    @property
    def system_prompt(self) -> str:
        return self._system_prompt

    @system_prompt.setter
    def system_prompt(self, text: str):
        self._system_prompt = text

    def add_user(self, content: str):
        self._messages.append(Message("user", content))

    def add_assistant(self, content: str):
        self._messages.append(Message("assistant", content))

    def add_tool_result(self, content: str):
        self._messages.append(Message("tool", content))

    def add_system(self, content: str):
        self._messages.append(Message("system", content))

    @property
    def last_user_message(self) -> Optional[str]:
        for m in reversed(self._messages):
            if m.role == "user":
                return m.content
        return None

    @property
    def message_count(self) -> int:
        return len(self._messages)

    def clear(self):
        self._messages.clear()

    # ── 上下文构建 ──

    def build_messages(self, new_user_msg: str = None) -> list[dict]:
        """构建 LLM API 格式的消息列表（含 system prompt + 裁剪后的历史）。

        Args:
            new_user_msg: 当前用户问题（追加到历史末尾）
        """
        messages = []

        # 1. System prompt
        if self._system_prompt:
            messages.append({"role": "system", "content": self._system_prompt})

        # 2. 裁剪后的历史消息
        trimmed = self._trim_history()
        messages.extend(m.to_dict() for m in trimmed)

        # 3. 当前用户消息
        if new_user_msg:
            messages.append({"role": "user", "content": new_user_msg})

        return messages

    def _trim_history(self) -> list[Message]:
        """裁剪历史：保留最近 N 轮 + 总字符数不超过 MAX_CONTEXT_CHARS。"""
        if not self._messages:
            return []

        # 从后往前累积，直到达到上限
        kept = []
        total_chars = 0
        for m in reversed(self._messages):
            total_chars += len(m.content)
            kept.insert(0, m)
            # 达到字符上限 或 达到轮次上限（user+assistant 对）
            user_assistant_count = sum(1 for x in kept if x.role in ("user", "assistant"))
            if (total_chars > self.MAX_CONTEXT_CHARS
                    or user_assistant_count > self.MAX_HISTORY_TURNS * 2):
                break

        return kept

    def get_history_summary(self) -> str:
        """获取对话摘要（用于调试/显示）。"""
        lines = []
        for m in self._messages[-6:]:  # 最近 6 条
            role = {"user": "👤", "assistant": "🤖", "tool": "🔧", "system": "⚙️"}.get(m.role, "?")
            preview = m.content[:80].replace("\n", " ")
            lines.append(f"{role} {preview}...")
        return "\n".join(lines) if lines else "(empty)"
