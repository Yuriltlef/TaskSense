"""TaskSense — 航空维护智能看板系统入口."""

import os
from pathlib import Path

# ── 模型缓存到项目目录，离线模式（大陆网络限制）──
_MODEL_CACHE = Path(__file__).parent / ".model_cache"
_MODEL_CACHE.mkdir(parents=True, exist_ok=True)
os.environ["HF_HOME"] = str(_MODEL_CACHE)
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

from app.ui.app import run

if __name__ == "__main__":
    run()
