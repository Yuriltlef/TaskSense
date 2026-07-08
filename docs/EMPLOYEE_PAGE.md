# 员工工作台页面 (EmployeeWorkbench)

## 概述

员工工作台是一线维修人员的个人操作页面，负责两个核心动作：

```
就绪(Ready) ──[接单]──▶ 执行中(In Progress) ──[提交验收]──▶ 验收中(Inspection)
```

以**独立子进程窗口**方式运行，与主应用通过 TCP Socket (JSON 行协议) 通信，支持多窗口并存。

## 架构

```
┌──────────────────────────────┐         TCP (127.0.0.1:随机端口)       ┌──────────────────────────────┐
│      主应用 (main.py)         │         JSON 行协议                     │    员工窗口子进程              │
│                              │                                        │    (employee_app.py)         │
│  SocketServer (daemon 线程)   │◀──── get_state / hash ───────────────│    SocketClient              │
│    ├─ bind 127.0.0.1:0       │───── 全量 state + hash ──────────────▶│      tag="employee"          │
│    ├─ 端口写入 server_port.txt │                                        │                              │
│    └─ dispatch: accept_task   │◀──── accept_task / block_task ───────│    发送操作命令               │
│                 block_task    │       submit_task                      │    后台 hash 轮询(1s)        │
│                 submit_task   │───── 执行结果 + 新 state ────────────▶│    变更时刷新 UI             │
│                              │                                        │                              │
│  State (内存权威数据源)        │        TCP 断连 → 检测 → 窗口关闭       │    page.window.close()       │
│  PersistenceService          │                                        │                              │
│    → data/board_state.json   │                                        │                              │
└──────────────────────────────┘                                        └──────────────────────────────┘
```

### IPC 协议

| 方向 | action | 说明 |
|------|--------|------|
| 子进程→主进程 | `get_state` | 获取全量 state + SHA256 hash，子进程初始加载 |
| 子进程→主进程 | `hash` | 仅获取 state 哈希，轻量变更检测 |
| 子进程→主进程 | `accept_task` | 员工接单（校验身份/状态/指派 → move_task→in_progress → save） |
| 子进程→主进程 | `block_task` | 员工阻塞任务（校验身份/状态/指派 → 写原因 → move_task→parts_hold → save） |
| 子进程→主进程 | `submit_task` | 员工提交验收（校验身份/状态/指派 → 写日志/工时 → move_task→inspection → save） |
| 子进程→主进程 | `shutdown` | 通知断连（close() 时发送，服务端忽略） |
| 主进程→子进程 | 响应 | `{"ok":true, "data":{...}}` 或 `{"ok":false, "error":"..."}` |

### 端口发现

- **主进程**：`SocketServer.start()` bind `127.0.0.1:0`（OS 分配随机端口）→ 写入 `data/server_port.txt`
- **子进程**：`SocketClient.__init__()` 调用 `_read_port()` 从 `data/server_port.txt` 读取端口 → TCP connect，最多重试 10 次（间隔 0.3s）

## 启动方式

### 主应用侧 (`board_page.py`)

```python
# 串行 spawn 队列：避免多个 Flutter 引擎同时初始化竞争 GPU
_spawn_queue: queue.Queue = queue.Queue()

def _spawn_worker():
    """后台线程：串行处理 spawn 请求，每个子进程连接成功后才发下一个。"""
    socket_server.on_connect = _on_subprocess_connected  # 连接回调 → 通知可以发下一个

    while True:
        kind, entry_name = _spawn_queue.get()
        _spawn_ready.wait(timeout=10.0)  # 等上一个连接成功

        subprocess.Popen(
            [sys.executable, entry_point, server_port],  # 端口号作为命令行参数传入
            cwd=project_root,
            stdout=err_log, stderr=err_log,
        )

def _open_employee_page(self):
    _ensure_spawn_worker()
    _spawn_queue.put(("employee", "employee_app.py"))
```

关键设计点：
- 串行启动：多个子进程不能同时 `Popen`——Flutter 引擎并行初始化会竞争 GPU 导致卡死
- 连接驱动：`socket_server.on_connect` 回调通知 worker 上一个子进程已连上，才发下一个
- stderr 重定向到 `data/logs/employee_stderr.log`，子进程日志用 `print(..., file=sys.stderr)`

### 入口脚本 (`employee_app.py`)

```python
if __name__ == "__main__":
    import flet as ft
    from app.employee.app import EmployeeWindowApp
    ft.app(target=EmployeeWindowApp().main)
```

每次启动打开一个独立 Flet 窗口，不加载 Agent/LLM 模块，内存轻量。

### 子进程连接流程

```
employee_app.py 启动
  → EmployeeWindowApp.main()
    → _create_ui()           ← 先渲染 UI 框架（标题栏 + body 槽位）
    → _show_connecting()     ← body 显示"正在连接..."（ProgressRing）
    → _connect_async()       ← 后台线程连接，不阻塞 UI
        → SocketClient(tag="employee")
        → client.get_state()       ← 拉取全量 state → 同步本地 state
        → client.start_polling(    ← 后台 hash 轮询
            1.0,
            on_change=self._on_external_change,  ← 变更时刷新工作台
            on_disconnect=lambda: self._do_close(),  ← 断连时关闭窗口
          )
        → page.run_task(_on_connected)  ← 切回主线程
    → show_login()           ← 切换到登录页
```

先渲染 UI 再连接是关键——`SocketClient()` 构造时同步阻塞 connect，如果放在 `main()` 开头，Flet 窗口会显示空白/卡死。

## 窗口结构

### 整体布局

```
┌────────────────── 1000px ──────────────────┐
│ ✈ 👤 员工工作台 - 张工     [─] [□] [✕]    │  自定义标题栏
├─────────────────────────────────────────────┤
│ Body                                         │
│  ┌─ 状态 A：登录选身份 ───────────────────┐  │
│  │  搜索框 + 员工列表 + 确认按钮           │  │
│  └────────────────────────────────────────┘  │
│  ┌─ 状态 B：任务工作台 ───────────────────┐  │
│  │  身份信息行 + [切换登录]               │  │
│  │  📋 待接单 [N]                          │  │
│  │    ┌─ 任务卡片 [接单] ──────────────┐  │  │
│  │  🔧 进行中 [N]                          │  │
│  │    ┌─ 任务卡片 [阻塞] [提交验收] ───┐  │  │
│  │  待接单 N 项 · 进行中 M 项              │  │
│  └────────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```

### 窗口设置

```python
# 与主应用一致的样式
self.page.window.frameless = False
self.page.window.title_bar_hidden = True
self.page.window.title_bar_buttons_hidden = True
self.page.window.bgcolor = ft.Colors.TRANSPARENT
# 注意：不设 prevent_close=True，走 Flet 原生快速关闭
```

## 状态同步

### SocketServer — 主进程侧 (`app/core/services/socket_server.py`)

单例 TCP 服务端，daemon 线程运行：

```python
class SocketServer:
    def start(self, preferred_port: int = 0) -> int:
        """bind 127.0.0.1:随机端口，写入 data/server_port.txt，启动 accept 循环。"""
        self._sock.bind(("127.0.0.1", preferred_port))
        self._port = self._sock.getsockname()[1]
        # 写端口到文件
        with open("data/server_port.txt", "w") as f:
            f.write(str(self._port))
        # 启动 accept 线程
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def _accept_loop(self):
        """循环 accept，每个客户端分配一个 handler 线程。"""
        while self._running:
            client, addr = self._sock.accept()
            threading.Thread(target=self._handle_client, args=(client, cid), daemon=True).start()

    def _handle_client(self, client, cid):
        """阻塞读取 JSON 行，解析 action → dispatch。"""
        buf = b""
        while self._running:
            chunk = client.recv(4096)
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                msg = json.loads(line.decode("utf-8"))
                resp = self._dispatch(msg, cid)
                client.sendall((json.dumps(resp) + "\n").encode("utf-8"))

    def _dispatch(self, msg, cid) -> dict:
        action = msg.get("action")
        if action == "get_state":   return {"ok": True, "data": {"state": state.to_dict(), "hash": _state_hash()}}
        if action == "hash":        return {"ok": True, "data": {"hash": _state_hash()}}
        if action == "accept_task": return self._handle_accept(params, cid)
        if action == "block_task":  return self._handle_block(params, cid)
        if action == "submit_task": return self._handle_submit(params, cid)
```

写操作处理流程（以 `accept_task` 为例）：
```
1. 参数校验：task_id 存在 / status==READY / employee_id 匹配 / 员工可用
2. 设 planned_start = now()
3. task_service.move_task(tid, "in_progress")
4. persistence_service.save()  ← 持久化到 board_state.json
5. 返回 {"ok": True, "data": {"state": state.to_dict(), "hash": _state_hash()}}
```

### SocketClient — 子进程侧 (`app/core/services/socket_client.py`)

```python
class SocketClient:
    def __init__(self, tag: str = "client", connect: bool = True):
        self._tag = tag
        if connect:
            self._connect()  # 读端口文件 → TCP connect，最多重试 10 次

    def _request(self, msg: dict) -> dict:
        """发送 JSON 行 + 接收一行响应。线程安全（_lock 保护）。"""
        with self._lock:
            self._send_raw(msg)
            return self._recv_response()

    def get_state(self) -> dict:
        """获取全量 state，返回 state dict。同时缓存 _last_hash。"""
        resp = self._request({"action": "get_state", "params": {}})
        self._last_hash = resp["data"]["hash"]
        return resp["data"]["state"]

    def get_hash(self) -> str:
        """仅获取 state 哈希（轻量，用于轮询变更检测）。"""
        resp = self._request({"action": "hash", "params": {}})
        return resp["data"]["hash"]

    def send_command(self, action, task_id, employee_id, employee_name, params=None) -> dict:
        """发送操作命令，返回执行后的新 state dict。"""
        resp = self._request({"action": action, "params": p})
        self._last_hash = resp["data"]["hash"]
        return resp["data"]["state"]

    def start_polling(self, interval=1.0, on_change=None, on_disconnect=None):
        """后台线程：每秒请求 hash，与 _last_hash 比较，变更时回调 on_change。"""
        def poll():
            while self._polling:
                h = self.get_hash()
                if h != self._last_hash:
                    self._last_hash = h
                    on_change()  # → 主线程刷新 UI
            # 循环退出 = 断连 → on_disconnect → page.window.close()
```

### 变更检测流程

```
子进程 poll 线程 (每 1s)
  → get_hash() → SHA256 前 16 位
  → 与本地 _last_hash 比较
  → 不同 → on_change 回调
    → WorkbenchPage.refresh()
      → client.get_state() → 拉取全量 state
      → state.load_from_dict() → 更新本地 state
      → 重建 UI
```

## 联动关闭

### 设计原则

- **不杀进程**：不用 taskkill/os._exit/WM_CLOSE
- **不拦截关闭**：`prevent_close` 全部移除，走 Flet 原生快速通道
- **TCP 断连即信号**：主进程关闭 server → 子进程 recv 失败 → 自动关闭窗口

### 关闭链路

```
主应用点 X / 自定义关闭按钮
  │
  ├─ _close_window() / _on_window_close()
  │    └─ socket_server.stop()
  │         ├─ self._running = False
  │         ├─ 遍历所有客户端 socket → shutdown(SHUT_RDWR) → close()
  │         ├─ 关闭监听 socket
  │         └─ 清理 data/server_port.txt
  │
  └─ page.window.close()                              ← 主窗口原生关闭

子进程 poll 线程 (每 1s 请求 hash)
  │
  ├─ recv() 返回空或抛出 ConnectionResetError
  ├─ _polling = False（退出轮询循环）
  └─ on_disconnect 回调
       └─ _do_close()
            ├─ self._client = None
            └─ page.window.close()                    ← 原生关闭自己
```

### 关键实现细节

**SocketClient.close() 的线程安全**：
```python
def close(self):
    self._polling = False
    if self._poll_thread and self._poll_thread is not threading.current_thread():
        self._poll_thread.join(timeout=3.0)  # 不在自己线程里 join 自己
    # 发送 shutdown 通知，然后关闭 socket
    self._send_raw({"action": "shutdown", "params": {}})
    self._sock.close()
```

**`_do_close()` 不调 `close()`**：因为 `_do_close` 在 poll 线程的 `on_disconnect` 回调内执行，此时 socket 已断开，不需要再 close。直接 `self._client = None; page.window.close()` 即可。

## 操作命令

员工操作通过 SocketClient 发送命令，主进程执行后即时返回新的全量 state：

```python
# workbench_page.py
def _do_accept(self, task):
    try:
        new_state = self._client.send_command(
            "accept_task",
            task_id=task.id,
            employee_id=self._employee_id,
            employee_name=self._employee_name,
        )
        state.load_from_dict(new_state)
        self.refresh()
    except Exception as e:
        Toast.show(self._page, f"接单失败: {e}", "error")
```

操作链路（以 `accept_task` 为例）：

```
用户点击 [接单]
  → send_command("accept_task", task_id, employee_id, employee_name)
    → SocketClient._request({"action":"accept_task", "params":{...}})
      → TCP send → 主进程 SocketServer._dispatch()
        → 校验失败 → 返回 {"ok":false, "error":"..."} → 子进程 throw RuntimeError
        → 校验成功 → move_task + save + 返回 {"ok":true, "data":{...}}
      → state.load_from_dict(data["state"])  ← 子进程同步本地 state
    → self.refresh()  ← 重建任务列表 UI
```

由于 TCP 往返延迟极低（<50ms），不再需要先改本地 state 再等后台纠正的"乐观更新"模式——操作结果直接从主进程的权威 state 加载，UI 始终展示正确数据。

## 身份系统

### 会话级身份

`app/core/state.py` 中两个字段：

```python
self.current_employee_id: str = ""    # 如 "ZH001"
self.current_employee_name: str = ""  # 如 "张工"
```

- 会话级有效，不持久化到 `to_dict()` / `load_from_dict()`
- 登录页选择员工 → 写入 → 切换状态 B
- "切换登录"按钮 → 清空 → 切回状态 A

## 双状态设计

### 状态 A：选择身份

- 搜索框实时过滤员工列表（姓名、ID、工种）
- 点击列表项选中高亮
- "确认身份"按钮写入 state，切换到状态 B

### 状态 B：任务列表

- 只显示归属当前员工的任务
- Ready 列：绿色"接单"按钮 → 确认弹窗 → send_command
- In Progress 列：黄色"阻塞" + 蓝色"提交验收"按钮
- 底部统计：待接单 N 项 · 进行中 M 项

## 文件清单

| 文件 | 说明 |
|------|------|
| `employee_app.py` | 子进程入口脚本 |
| `app/employee/app.py` | 窗口应用：登录/工作台视图切换、窗口设置、连接管理、关闭逻辑 |
| `app/employee/pages/login_page.py` | 登录页：员工搜索/选择 |
| `app/employee/pages/workbench_page.py` | 工作台页：任务列表 + 通过 SocketClient 接单/阻塞/提交 |
| `app/core/services/socket_server.py` | 主进程 TCP 服务端：端口管理、JSON 行协议、命令 dispatch、hash 计算 |
| `app/core/services/socket_client.py` | 子进程 TCP 客户端：端口发现、请求-响应、hash 轮询、断连检测 |
| `app/core/services/persistence_service.py` | 主应用持久化：filelock 保护 board_state.json 读写 |
| `app/ui/pages/board_page.py` | 主应用：串行 spawn 队列启动子进程 |
| `app/ui/app.py` | 主应用：启动 socket_server、关闭时 stop |
| `data/server_port.txt` | 端口发现文件：主进程写入，子进程读取（运行时生成） |

## 关键设计决策

1. **子进程而非线程**：员工窗口完全独立的 Python 进程，崩溃不影响主应用，不加载 Agent/LLM 模块，内存轻量
2. **TCP Socket 通信**：JSON 行协议，主进程为权威数据源，写操作即时返回结果（<50ms），hash 轮询检测外部变更（<1s）
3. **串行 spawn 队列**：多个 Flutter 引擎同时初始化会竞争 GPU 导致卡死，通过连接信号驱动的串行队列逐个启动
4. **TCP 断连关闭**：主进程关闭 server socket → 子进程 recv 检测断连 → 自行 `close()`，不杀进程、不找窗口句柄、不依赖信号文件
5. **先渲染 UI 再连接**：`SocketClient()` 构造时同步阻塞 connect，放在后台线程执行，UI 先显示"正在连接"避免空白/卡死窗口
6. **移除 `prevent_close`**：走 Flet 原生快速关闭通道，`close()` 可在任意线程调用（底层 `PostMessage(WM_CLOSE)` 线程安全）
