"""TaskSense — 航空维护智能看板系统入口."""

from pathlib import Path

# ── 修复 Windows 退出时 "Event loop is closed" 报错 ──
# Flet 依赖 ProactorEventLoop 启动子进程，不能换 Selector。
# 错误出在 StreamWriter.__del__ 在事件循环关闭后才被 GC 调用。
# 这里猴子补丁一下，忽略退出时的这个无害报错。
import asyncio.streams
_original_del = asyncio.streams.StreamWriter.__del__
def _safe_del(self):
    try:
        _original_del(self)
    except RuntimeError:
        pass  # 事件循环已关闭，资源已由 OS 回收，忽略
asyncio.streams.StreamWriter.__del__ = _safe_del

# ── 模型缓存到项目目录 ──
from app.knowledge.cache_utils import setup_model_cache
setup_model_cache(Path(__file__).parent)

# ── 后台预加载嵌入模型 + 知识库 ──
# 避免首次提问时等待模型加载（GPU 模型加载需 3-10 秒）
from app.agent.preload import preload_async
_preload_thread = preload_async()

from app.ui.app import run

if __name__ == "__main__":
    run()
