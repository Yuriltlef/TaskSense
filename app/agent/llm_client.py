"""LLM 客户端 — 支持 OpenAI-compatible API."""

from openai import OpenAI


class LLMClient:
    """统一的 LLM 调用客户端。

    从 settings.json 实时读取配置，支持：
    - anthropic (via OpenAI-compatible proxy)
    - openai
    - 任何 OpenAI-compatible API

    设置更新后无需重启应用 —— chat() 每次调用都会检查配置变化。
    """

    def __init__(self):
        self._client = None
        self._cached_key: str = ""
        self._cached_url: str = ""

    def _get_settings(self) -> dict:
        """实时读取 LLM 配置节。"""
        from app.config.settings_manager import SettingsManager
        return SettingsManager().get_section("llm")

    def _ensure_client(self):
        """确保 _client 与当前设置同步。"""
        cfg = self._get_settings()
        api_key = cfg.get("api_key", "")
        base_url = cfg.get("base_url", "https://api.anthropic.com")

        if not api_key:
            self._client = None
            self._cached_key = ""
            self._cached_url = ""
            return None

        # 设置未变则复用已有客户端
        if self._client is not None and api_key == self._cached_key and base_url == self._cached_url:
            return self._client

        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._cached_key = api_key
        self._cached_url = base_url
        return self._client

    @property
    def is_available(self) -> bool:
        """LLM 是否已配置且可用（仅检查 key 存在，不验证有效性）。"""
        return bool(self._get_settings().get("api_key"))

    @property
    def model(self) -> str:
        return self._get_settings().get("model", "claude-sonnet-4-6")

    @property
    def temperature(self) -> float:
        return float(self._get_settings().get("temperature", 0.0))

    @property
    def max_tokens(self) -> int:
        return int(self._get_settings().get("max_tokens", 4096))

    def chat(self, system_prompt: str, user_message: str) -> str:
        """发送单轮聊天请求（遗留接口）。"""
        return self.chat_messages([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ])

    def chat_messages(self, messages: list[dict]) -> str:
        """发送多轮对话请求。

        Args:
            messages: [{"role": "...", "content": "..."}, ...]
                      支持 system/user/assistant/tool 角色

        Returns:
            LLM 回复文本，或 [Error] 前缀的错误消息
        """
        client = self._ensure_client()
        if not client:
            return "[Error] LLM client not configured. Set api_key in settings.json."

        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                timeout=30.0,  # 30s 超时
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"[Error] LLM call failed: {e}"


# 全局单例 —— 内部不缓存配置，每次调用实时读取 SettingsManager
llm = LLMClient()
