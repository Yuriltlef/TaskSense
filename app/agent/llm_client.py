"""LLM 客户端 — 支持 OpenAI-compatible API."""

from openai import OpenAI


class LLMClient:
    """统一的 LLM 调用客户端。

    从 settings.json 读取配置，支持：
    - anthropic (via OpenAI-compatible proxy)
    - openai
    - 任何 OpenAI-compatible API
    """

    def __init__(self):
        from app.config.settings_manager import SettingsManager
        mgr = SettingsManager()
        mgr.load()
        cfg = mgr.get_section("llm")

        self.provider = cfg.get("provider", "anthropic")
        self.model = cfg.get("model", "claude-sonnet-4-6")
        self.api_key = cfg.get("api_key", "")
        self.base_url = cfg.get("base_url", "https://api.anthropic.com")
        self.temperature = float(cfg.get("temperature", 0.0))
        self.max_tokens = int(cfg.get("max_tokens", 4096))

        if self.api_key:
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )
        else:
            self._client = None

    @property
    def is_available(self) -> bool:
        return self._client is not None and bool(self.api_key)

    def chat(self, system_prompt: str, user_message: str) -> str:
        """发送聊天请求。

        Args:
            system_prompt: 系统提示词
            user_message: 用户消息

        Returns:
            LLM 回复文本
        """
        if not self._client:
            return "[Error] LLM client not configured. Set api_key in settings.json."

        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"[Error] LLM call failed: {e}"


# 全局单例
llm = LLMClient()
