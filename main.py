"""TaskSense — 航空维护智能看板系统入口."""

import os
from pathlib import Path

# ── 修复 Windows 退出时 "Event loop is closed" 报错 ──
# Flet 依赖 ProactorEventLoop 启动子进程，不能换 Selector。
# 错误出在 StreamWriter.__del__ 在事件循环关闭后才被 GC 调用。
# 这里猴子补丁一下，忽略退出时的这个无害报错。
import asyncio
import asyncio.streams
_original_del = asyncio.streams.StreamWriter.__del__
def _safe_del(self):
    try:
        _original_del(self)
    except RuntimeError:
        pass  # 事件循环已关闭，资源已由 OS 回收，忽略
asyncio.streams.StreamWriter.__del__ = _safe_del

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
