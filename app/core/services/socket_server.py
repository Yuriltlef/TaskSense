"""Socket 服务端 — 主进程 TCP server，处理子进程请求。

协议：JSON 行协议（每行一个 JSON object + \n）
- 请求: {"action": "get_state"|"accept_task"|"block_task"|"submit_task", "params": {...}}
- 响应: {"ok": true, "data": {...}} 或 {"ok": false, "error": "..."}

端口写入 data/server_port.txt，子进程启动时读取。
"""

import json
import os
import socket
import threading
import hashlib
from datetime import datetime
from typing import Optional

from app.core.services.employee_service import employee_service
from app.core.services.task_service import task_service
from app.core.state import state
from app.core.logging import log


def _resolve_path(path: str) -> str:
    if not os.path.isabs(path):
        project_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..")
        )
        path = os.path.join(project_root, path)
    return path


def _state_hash() -> str:
    """计算当前状态的简短哈希，用于轻量变更检测。"""
    data = state.to_dict()
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class SocketServer:
    """主进程 TCP 服务端（单例，后台线程）。"""

    _instance: Optional["SocketServer"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._port: int = 0
        self._sock: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._clients: list[socket.socket] = []
        self._clients_lock = threading.Lock()
        self._client_count = 0
        self.on_connect = None  # 新客户端连接回调，供 spawn 队列使用

    # ── 公开 API ──

    @property
    def port(self) -> int:
        return self._port

    def start(self, preferred_port: int = 0) -> int:
        """启动服务端。返回实际绑定的端口。"""
        if self._running:
            return self._port

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", preferred_port))
        self._sock.listen(5)
        self._port = self._sock.getsockname()[1]
        self._running = True

        port_path = _resolve_path("data/server_port.txt")
        os.makedirs(os.path.dirname(port_path), exist_ok=True)
        with open(port_path, "w") as f:
            f.write(str(self._port))

        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()
        log.info("srv.start", f"port={self._port}")
        return self._port

    def stop(self):
        """停止服务端，断开所有客户端。"""
        if not self._running:
            return
        self._running = False

        with self._clients_lock:
            count = len(self._clients)
            for c in self._clients:
                try:
                    c.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    c.close()
                except OSError:
                    pass
            self._clients.clear()

        log.info("srv.stop", f"clients={count}")

        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

        port_path = _resolve_path("data/server_port.txt")
        try:
            os.unlink(port_path)
        except OSError:
            pass

    # ── 内部 ──

    def _accept_loop(self):
        while self._running:
            try:
                self._sock.settimeout(0.5)
                client, addr = self._sock.accept()
                cid = self._client_count = self._client_count + 1
                client.settimeout(None)
                with self._clients_lock:
                    self._clients.append(client)
                log.info("srv.connect", f"#{cid} {addr[0]}:{addr[1]}")
                if self.on_connect:
                    try:
                        self.on_connect()
                    except Exception:
                        pass
                t = threading.Thread(target=self._handle_client,
                                     args=(client, cid), daemon=True)
                t.start()
            except socket.timeout:
                continue
            except OSError:
                if self._running:
                    log.warn("srv", "accept error")
                break

    def _handle_client(self, client: socket.socket, cid: int):
        """处理单个客户端连接（阻塞读取 JSON 行）。"""
        buf = b""
        try:
            while self._running:
                chunk = client.recv(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line.decode("utf-8"))
                        action = msg.get("action", "?")
                        log.info("srv.req", f"#{cid} {action}")
                        resp = self._dispatch(msg, cid)
                        resp_bytes = (json.dumps(resp, ensure_ascii=False) + "\n").encode("utf-8")
                        client.sendall(resp_bytes)
                    except json.JSONDecodeError:
                        log.warn("srv", f"#{cid} invalid json")
                        err = json.dumps({"ok": False, "error": "invalid json"}, ensure_ascii=False)
                        client.sendall((err + "\n").encode("utf-8"))
        except (ConnectionResetError, BrokenPipeError, OSError):
            pass
        finally:
            with self._clients_lock:
                if client in self._clients:
                    self._clients.remove(client)
            try:
                client.close()
            except OSError:
                pass
            log.info("srv.disconnect", f"#{cid}")

    def _dispatch(self, msg: dict, cid: int) -> dict:
        action = msg.get("action", "")
        params = msg.get("params", {})

        try:
            if action == "get_state":
                return self._handle_get_state()
            elif action == "hash":
                return {"ok": True, "data": {"hash": _state_hash()}}
            elif action == "accept_task":
                return self._handle_accept(params, cid)
            elif action == "block_task":
                return self._handle_block(params, cid)
            elif action == "submit_task":
                return self._handle_submit(params, cid)
            elif action == "shutdown":
                return {"ok": True, "data": {"message": "bye"}}
            else:
                log.warn("srv", f"#{cid} unknown action: {action}")
                return {"ok": False, "error": f"unknown action: {action}"}
        except Exception as e:
            log.warn("srv.err", f"#{cid} {action}: {e}")
            return {"ok": False, "error": str(e)}

    # ── 动作处理 ──

    def _handle_get_state(self) -> dict:
        data = state.to_dict()
        h = _state_hash()
        return {"ok": True, "data": {"state": data, "hash": h}}

    def _handle_accept(self, params: dict, cid: int) -> dict:
        tid = params["task_id"]
        ename = params.get("employee_name", "?")
        task = state.get_task(tid)
        if not task:
            raise ValueError(f"任务 {tid} 不存在")
        from app.core.models.task import TaskStatus
        if task.status != TaskStatus.READY:
            raise ValueError(f"状态={task.status.value}，非就绪")
        if task.employee_id != params.get("employee_id", ""):
            raise ValueError("任务未指派给该员工")
        if not employee_service.validate(params.get("employee_id", "")):
            raise ValueError(f"员工 {params.get('employee_id')} 不可用")

        if not task.planned_start:
            task_service.update_task(tid, planned_start=datetime.now())
        task_service.move_task(tid, "in_progress", changed_by=ename)

        from app.core.services.persistence_service import persistence_service
        persistence_service.save()

        log.info("srv.accept", f"#{cid} task={tid[:8]} worker={ename}")
        return self._handle_get_state()

    def _handle_block(self, params: dict, cid: int) -> dict:
        tid = params["task_id"]
        ename = params.get("employee_name", "?")
        reason = params.get("reason", "").strip()
        if not reason:
            raise ValueError("阻塞原因不能为空")
        task = state.get_task(tid)
        if not task:
            raise ValueError(f"任务 {tid} 不存在")
        from app.core.models.task import TaskStatus
        if task.status != TaskStatus.IN_PROGRESS:
            raise ValueError(f"状态={task.status.value}，非执行中")
        if task.employee_id != params.get("employee_id", ""):
            raise ValueError("任务未指派给该员工")
        if not employee_service.validate(params.get("employee_id", "")):
            raise ValueError(f"员工 {params.get('employee_id')} 不可用")

        task_service.block_task(tid, reason=reason, user=ename)

        from app.core.services.persistence_service import persistence_service
        persistence_service.save()

        log.info("srv.block", f"#{cid} task={tid[:8]} worker={ename} reason={reason[:20]}")
        return self._handle_get_state()

    def _handle_submit(self, params: dict, cid: int) -> dict:
        tid = params["task_id"]
        ename = params.get("employee_name", "?")
        handover_log = params.get("handover_log", "").strip()
        actual_hours = float(params.get("actual_hours", 0))
        if not handover_log:
            raise ValueError("交接班日志不能为空")
        task = state.get_task(tid)
        if not task:
            raise ValueError(f"任务 {tid} 不存在")
        from app.core.models.task import TaskStatus
        if task.status != TaskStatus.IN_PROGRESS:
            raise ValueError(f"状态={task.status.value}，非执行中")
        if task.employee_id != params.get("employee_id", ""):
            raise ValueError("任务未指派给该员工")
        if not employee_service.validate(params.get("employee_id", "")):
            raise ValueError(f"员工 {params.get('employee_id')} 不可用")

        task_service.update_task(
            tid, shift_handover_log=handover_log, actual_hours=actual_hours)
        task_service.move_task(tid, "inspection", changed_by=ename)

        from app.core.services.persistence_service import persistence_service
        persistence_service.save()

        log.info("srv.submit", f"#{cid} task={tid[:8]} worker={ename} hours={actual_hours}")
        return self._handle_get_state()


# 全局单例
socket_server = SocketServer()
