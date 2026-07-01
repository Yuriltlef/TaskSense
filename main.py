"""TaskSense — 航空维护智能看板系统入口."""

import os
from pathlib import Path

# ── 模型缓存到项目目录 ──
_MODEL_CACHE = Path(__file__).parent / ".model_cache"
_MODEL_CACHE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("HF_HOME", str(_MODEL_CACHE))

# 检查嵌入模型是否已缓存
_MODEL_NAME = "BAAI/bge-m3"
_MODEL_SLUG = "models--" + _MODEL_NAME.replace("/", "--")
_MODEL_SNAPSHOTS = _MODEL_CACHE / "hub" / _MODEL_SLUG / "snapshots"
_IS_CACHED = _MODEL_SNAPSHOTS.exists() and any(_MODEL_SNAPSHOTS.iterdir())
if _IS_CACHED:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"

from app.ui.app import run

if __name__ == "__main__":
    run()
