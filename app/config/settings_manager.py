"""设置管理器 — 持久化 JSON + 环境变量覆盖。

用法:
    from app.config.settings_manager import SettingsManager
    mgr = SettingsManager()
    mgr.load()
    api_key = mgr.get("llm", "api_key")

环境变量覆盖（优先级高于 JSON）:
    TASKSENSE_LLM__API_KEY=sk-xxx
"""

import json
import os
from pathlib import Path


SETTINGS_FILE = "settings.json"

DEFAULT_SETTINGS = {
    # ── LLM / API ──
    "llm": {
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
        "api_key": "",
        "base_url": "https://api.anthropic.com",
        "temperature": 0.0,
        "max_tokens": 4096,
    },
    # ── RAG ──
    "rag": {
        "embedding_model": "all-MiniLM-L6-v2",
        "vector_store": "chroma",
        "chunk_size": 800,
        "chunk_overlap": 120,
        "retrieval_top_k": 10,
    },
    # ── UI ──
    "ui": {
        "theme": "dark",
        "language": "zh",
        "scale": 1.2,
        "card_preview_delay_ms": 300,
        "default_swimlane": "",
    },
    # ── Agent ──
    "agent": {
        "triage_autonomy": "low",
        "suggest_autonomy": "medium",
        "compliance_autonomy": "high",
        "anomaly_check_interval_minutes": 30,
    },
}


class SettingsManager:
    """全局设置管理 — 加载/保存 settings.json。"""

    _instance = None
    _data: dict = {}
    _path: str = ""

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def load(cls, path: str = SETTINGS_FILE) -> dict:
        cls._path = path
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                cls._data = cls._merge(DEFAULT_SETTINGS, saved)
            except Exception:
                cls._data = dict(DEFAULT_SETTINGS)
        else:
            cls._data = dict(DEFAULT_SETTINGS)
        return cls._data

    @classmethod
    def save(cls) -> str:
        with open(cls._path or SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(cls._data, f, ensure_ascii=False, indent=2)
        return cls._path or SETTINGS_FILE

    @classmethod
    def get(cls, section: str, key: str, default=None):
        return cls._data.get(section, {}).get(key, default)

    @classmethod
    def set(cls, section: str, key: str, value):
        if section not in cls._data:
            cls._data[section] = {}
        cls._data[section][key] = value

    @classmethod
    def get_section(cls, section: str) -> dict:
        return cls._data.get(section, {}) if cls._data else DEFAULT_SETTINGS.get(section, {})

    @classmethod
    def get_all(cls) -> dict:
        return cls._data if cls._data else dict(DEFAULT_SETTINGS)

    @classmethod
    def from_env(cls):
        """用环境变量覆盖当前加载的设置（TASKSENSE_ 前缀）。

        环境变量格式: TASKSENSE_SECTION__KEY=value
        例: TASKSENSE_LLM__API_KEY=sk-xxx
        """
        cls.load()  # ensure loaded
        for env_key, env_val in os.environ.items():
            if not env_key.startswith("TASKSENSE_"):
                continue
            # TASKSENSE_LLM__API_KEY → section="llm", key="api_key"
            parts = env_key[len("TASKSENSE_"):].lower().split("__", 1)
            if len(parts) == 2:
                section, key = parts
                # 类型转换
                default_val = cls.get(section, key)
                if isinstance(default_val, bool):
                    env_val = env_val.lower() in ("1", "true", "yes")
                elif isinstance(default_val, int):
                    env_val = int(env_val)
                elif isinstance(default_val, float):
                    env_val = float(env_val)
                cls.set(section, key, env_val)

    @classmethod
    def _merge(cls, defaults: dict, saved: dict) -> dict:
        """深度合并：saved 覆盖 defaults，但保留 defaults 中的新字段。"""
        result = {}
        for k, v in defaults.items():
            if k in saved and isinstance(v, dict) and isinstance(saved[k], dict):
                result[k] = cls._merge(v, saved[k])
            elif k in saved:
                result[k] = saved[k]
            else:
                result[k] = v
        return result


# 初始化
_settings_manager = SettingsManager()
_settings_manager.load()
