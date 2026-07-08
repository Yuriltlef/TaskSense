"""Socket 客户端 — 子进程连接主进程，替代 StateSync + command_queue。

用法:
    client = SocketClient()
    state_dict = client.get_state()       # 获取全量 state
    state.load_from_dict(state_dict)      # 恢复到本地 state
    client.send_command("accept_task", task_id=..., ...)  # 发送命令
    client.start_polling(1.0, on_change)  # 后台轮询 hash，变更时回调
    client.close()                        # 断开连接
"""

import json
import os
import socket
import sys
import threading
import time
from datetime import datetime
from typing import Callable, Optional


def _resolve_path(path: str) -> str:
    if not os.path.isabs(path):
        project_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..")
        )
        path = os.path.join(project_root, path)
    return path


def _read_port() -> int:
    """从 data/server_port.txt 读取主进程端口。"""
    path = _resolve_path("data/server_port.txt")
    if not os.path.exists(path):
        raise RuntimeError(f"服务端口文件不存在: {path}")
    with open(path, "r") as f:
        return int(f.read().strip())


def _log(msg: str):
    """子进程日志：带时间戳写入 stderr（由主进程重定向到 data/logs/xxx_stderr.log）。"""
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{ts}] {msg}", file=sys.stderr, flush=True)


class SocketClient:
    """子进程 TCP 客户端。

    连接主进程的 SocketServer，提供：
    - get_state()：获取全量状态
    - send_command()：发送操作命令并获取最新状态
    - start_polling()：后台轻量 hash 轮询，变更时回调
    """

    def __init__(self, tag: str = "client", connect: bool = True):
        self._tag = tag  # 标识：employee / taskboard / gantt
        self._sock: Optional[socket.socket] = None
        self._lock = threading.Lock()
        self._polling = False
        self._poll_thread: Optional[threading.Thread] = None
        self._last_hash: str = ""

        if connect:
            self._connect()

    @property
    def tag(self) -> str:
        return self._tag

    # ── 连接 ──

    def _connect(self):
        port = _read_port()
        _log(f"[{self._tag}] connecting port={port}")
        for attempt in range(1, 11):
            try:
                self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._sock.settimeout(2.0)
                self._sock.connect(("127.0.0.1", port))
                self._sock.settimeout(None)
                _log(f"[{self._tag}] connected (attempt={attempt})")
                return
            except (ConnectionRefusedError, socket.timeout, OSError) as e:
                self._sock.close()
                self._sock = None
                if attempt == 10:
                    raise ConnectionError(f"连接主应用失败（{attempt}次重试）: {e}")
                time.sleep(0.3)
                _log(f"[{self._tag}] retry {attempt}: {type(e).__name__}")

    def close(self):
        _log(f"[{self._tag}] close()")
        self._polling = False
        if self._poll_thread and self._poll_thread is not threading.current_thread():
            self._poll_thread.join(timeout=3.0)
        self._poll_thread = None
        with self._lock:
            if self._sock:
                try:
                    self._send_raw({"action": "shutdown", "params": {}})
                except OSError:
                    pass
                try:
                    self._sock.close()
                except OSError:
                    pass
                self._sock = None

    # ── 请求-响应 ──

    def _send_raw(self, msg: dict):
        data = (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")
        self._sock.sendall(data)

    def _request(self, msg: dict) -> dict:
        with self._lock:
            self._send_raw(msg)
            return self._recv_response()

    def _recv_response(self) -> dict:
        buf = b""
        while True:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise ConnectionError("与主应用断开连接")
            buf += chunk
            if b"\n" in buf:
                line, _ = buf.split(b"\n", 1)
                return json.loads(line.decode("utf-8"))

    def get_state(self) -> dict:
        resp = self._request({"action": "get_state", "params": {}})
        if not resp.get("ok"):
            raise RuntimeError(resp.get("error", "获取状态失败"))
        data = resp["data"]
        self._last_hash = data.get("hash", "")
        tasks = len(data["state"].get("tasks", {}))
        _log(f"[{self._tag}] get_state tasks={tasks}")
        return data["state"]

    def get_hash(self) -> str:
        resp = self._request({"action": "hash", "params": {}})
        if not resp.get("ok"):
            raise RuntimeError(resp.get("error", "获取哈希失败"))
        return resp["data"]["hash"]

    def send_command(self, action: str, task_id: str,
                     employee_id: str = "", employee_name: str = "",
                     params: dict | None = None) -> dict:
        p = params or {}
        p["task_id"] = task_id
        p["employee_id"] = employee_id
        p["employee_name"] = employee_name

        _log(f"[{self._tag}] send {action} task={task_id[:8]} worker={employee_name}")
        resp = self._request({"action": action, "params": p})
        if not resp.get("ok"):
            raise RuntimeError(resp.get("error", "命令执行失败"))
        data = resp["data"]
        self._last_hash = data.get("hash", "")
        return data["state"]

    # ── 后台轮询 ──

    def start_polling(self, interval: float = 1.0,
                       on_change: Optional[Callable] = None,
                       on_disconnect: Optional[Callable] = None):
        if self._polling:
            return
        self._polling = True

        def poll():
            while self._polling:
                try:
                    h = self.get_hash()
                    if h != self._last_hash:
                        _log(f"[{self._tag}] state changed hash={h[:8]}")
                        self._last_hash = h
                        if on_change:
                            on_change()
                except Exception as e:
                    self._polling = False
                    _log(f"[{self._tag}] disconnected: {type(e).__name__}")
                    if on_disconnect:
                        _log(f"[{self._tag}] → on_disconnect")
                        try:
                            on_disconnect()
                        except Exception as exc:
                            _log(f"[{self._tag}] on_disconnect error: {exc}")
                    return
                for _ in range(int(interval / 0.1)):
                    if not self._polling:
                        return
                    time.sleep(0.1)

        self._poll_thread = threading.Thread(target=poll, daemon=True)
        self._poll_thread.start()

    def stop_polling(self):
        self._polling = False
