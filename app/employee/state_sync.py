"""跨进程状态同步服务 — 员工窗口侧。

只从 data/employee_state.json（主应用写入的 API 文件）读取状态。
不直接读取 board_state.json——所有数据通过主应用中转。
同时检测主应用发出的关闭信号，优雅退出。
"""

import json
import os
import threading
import time
from typing import Callable, Optional


def _resolve_path(path: str) -> str:
    if not os.path.isabs(path):
        # app/employee/state_sync.py → 往上 2 层到项目根
        project_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        path = os.path.join(project_root, path)
    return path


class StateSync:
    """员工窗口状态同步器。

    轮询 data/employee_state.json（主应用写入的只读 API 副本），
    不直接读取 data/board_state.json。
    同时检测 data/shutdown.signal 实现优雅关闭。
    """

    def __init__(self, filepath: str = "data/employee_state.json"):
        self._path = _resolve_path(filepath)
        self._shutdown_path = _resolve_path("data/shutdown.signal")
        self._last_mtime: float = 0.0
        self._listeners: list[Callable] = []
        self._on_shutdown: Optional[Callable] = None
        self._polling: bool = False
        self._poll_thread: Optional[threading.Thread] = None
        self._tick_counter: int = 0

    # ── 读取 ──

    def read_state(self) -> bool:
        """读取 employee_state.json 并加载到内存 AppState。"""
        if not os.path.exists(self._path):
            return False
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            from app.core.state import state
            state.load_from_dict(data)
            self._last_mtime = os.path.getmtime(self._path)
            return True
        except (json.JSONDecodeError, IOError) as e:
            print(f"[StateSync] 读取失败: {e}")
            return False

    # ── 变更检测 ──

    def has_external_changes(self) -> bool:
        try:
            current = os.path.getmtime(self._path)
        except OSError:
            return False
        return current != self._last_mtime

    # ── 轮询 ──

    def start_polling(self, interval: float = 2.0,
                       on_change: Optional[Callable] = None,
                       on_shutdown: Optional[Callable] = None):
        if on_change:
            self._listeners.append(on_change)
        if on_shutdown:
            self._on_shutdown = on_shutdown
        if self._polling:
            return
        # 清理上次可能残留的关闭信号
        if os.path.exists(self._shutdown_path):
            try:
                os.unlink(self._shutdown_path)
            except OSError:
                pass
        self._polling = True
        self._poll_thread = threading.Thread(
            target=self._poll_loop, args=(interval,), daemon=True)
        self._poll_thread.start()

    def stop_polling(self):
        self._polling = False

    def _poll_loop(self, interval: float):
        # 用细粒度 sleep 确保关闭信号能快速响应
        tick = 0.25  # 每 0.25s 检查一次
        while self._polling:
            try:
                # 1. 优先检测关闭信号
                if os.path.exists(self._shutdown_path):
                    self._polling = False
                    if self._on_shutdown:
                        try:
                            self._on_shutdown()
                        except Exception:
                            pass
                    return

                # 2. 检测状态变更（每隔 interval 秒才做一次完整检查）
                if self._tick_counter is None:
                    self._tick_counter = 0
                self._tick_counter += 1
                if self._tick_counter >= int(interval / tick):
                    self._tick_counter = 0
                    if self.has_external_changes():
                        self.read_state()
                        for listener in self._listeners:
                            try:
                                listener()
                            except Exception:
                                pass
            except Exception:
                pass
            time.sleep(tick)
