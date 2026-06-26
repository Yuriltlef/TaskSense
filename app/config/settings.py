"""全局配置 — 支持环境变量覆盖."""

import os
from dataclasses import dataclass, field


@dataclass
class AppSettings:
    """应用全局配置。

    所有配置项可通过环境变量 TASKSENSE_<FIELD> 覆盖。
    """

    # ── 应用 ──
    app_name: str = "TaskSense"
    app_version: str = "0.1.0"
    debug: bool = False

    # ── LLM ──
    llm_provider: str = "anthropic"
    llm_model: str = "claude-sonnet-4-6"
    llm_temperature: float = 0.0
    llm_max_tokens: int = 4096

    # ── 嵌入模型 ──
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536

    # ── 向量存储 ──
    vector_store_type: str = "chroma"
    vector_store_path: str = "./data/vector_store"

    # ── RAG ──
    chunk_size: int = 800
    chunk_overlap: int = 120
    retrieval_top_k: int = 10
    hybrid_alpha: float = 0.5

    # ── Agent ──
    triage_autonomy: str = "low"
    suggest_autonomy: str = "medium"
    compliance_autonomy: str = "high"
    anomaly_check_interval_minutes: int = 30

    # ── UI ──
    theme_mode: str = "dark"
    language: str = "zh"
    default_swimlane: str = ""
    card_preview_delay_ms: int = 300

    # ── 数据 ──
    db_path: str = "./data/app.db"
    knowledge_base_path: str = "./data/knowledge_base"

    @classmethod
    def from_env(cls) -> "AppSettings":
        """从环境变量加载配置。环境变量前缀: TASKSENSE_"""
        settings = cls()
        for field_name in cls.__dataclass_fields__:
            env_key = f"TASKSENSE_{field_name.upper()}"
            env_value = os.environ.get(env_key)
            if env_value is not None:
                field_type = type(getattr(settings, field_name))
                if field_type is bool:
                    setattr(settings, field_name, env_value.lower() in ("1", "true", "yes"))
                elif field_type is int:
                    setattr(settings, field_name, int(env_value))
                elif field_type is float:
                    setattr(settings, field_name, float(env_value))
                else:
                    setattr(settings, field_name, env_value)
        return settings


# 全局配置实例
settings = AppSettings.from_env()
