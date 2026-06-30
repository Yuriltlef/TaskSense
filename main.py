"""TaskSense — 航空维护智能看板系统入口."""

import os
from pathlib import Path

# 模型缓存到项目目录
_MODEL_CACHE = Path(__file__).parent / ".model_cache"
os.environ.setdefault("HF_HOME", str(_MODEL_CACHE))
_MODEL_CACHE.mkdir(parents=True, exist_ok=True)

from app.ui.app import run

if __name__ == "__main__":
    run()
