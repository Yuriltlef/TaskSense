# 员工工作台页面 (EmployeeWorkbench)

## 概述

员工工作台是一线维修人员的个人操作页面，负责两个核心动作：

```
就绪(Ready) ──[接单]──▶ 执行中(In Progress) ──[提交验收]──▶ 验收中(Inspection)
```

以**独立子进程窗口**方式运行，与主应用通过文件 IPC 通信，支持多窗口并存。

## 架构

```
┌─────────────────────┐                      ┌─────────────────────┐
│   主应用 (main.py)   │                      │  员工窗口子进程       │
│                     │  pending_commands.json │                     │
│  轮询处理命令        │ ◀────────────────── │  发送操作命令         │
│                     │                      │                     │
│  写入状态快照        │ ─── employee_state.json ──▶ │  轮询 mtime 刷新 UI  │
│                     │                      │                     │
│  写入关闭信号        │ ─── shutdown.signal ──▶ │  检测信号 → 自行关闭  │
└─────────────────────┘                      └─────────────────────┘
```

### IPC 三条通道

| 通道 | 方向 | 文件 | 主应用侧 | 员工侧 |
|------|------|------|---------|--------|
| 命令 | 员工→主应用 | `data/pending_commands.json` | 轮询(0.5s) → 执行 + 保存 | `send_command()` 写入 |
| 状态 | 主应用→员工 | `data/employee_state.json` | `PersistenceService.save()` 同步写入 | `StateSync` 轮询(1s) mtime |
| 关闭 | 主应用→员工 | `data/shutdown.signal` | `shutdown_employee_processes()` 写入 | `StateSync` 轮询(0.25s) 检测 → `_do_close()` |

## 启动方式

### 主应用侧 (`board_page.py`)

```python
def _open_employee_page(self):
    """启动员工工作台为独立子进程窗口。失败时回退 overlay。"""
    import subprocess, sys, os

    project_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..")
    )
    entry_point = os.path.join(project_root, "employee_app.py")

    try:
        proc = subprocess.Popen(
            [sys.executable, entry_point],
            cwd=project_root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _employee_processes.append(proc)  # 跟踪子进程
    except Exception:
        # 回退到 overlay 模式
        from app.ui.pages.employee_page import EmployeeWorkbench
        EmployeeWorkbench.open(self._page)
```

### 入口脚本 (`employee_app.py`)

```python
if __name__ == "__main__":
    import flet as ft
    from app.employee.app import EmployeeWindowApp
    ft.app(target=EmployeeWindowApp().main)
```

每次启动打开一个独立 Flet 窗口，不加载 Agent/LLM 模块，内存轻量。

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

### 员工侧 (`state_sync.py`)

```python
class StateSync:
    def __init__(self, filepath: str = "data/employee_state.json"):
        self._path = _resolve_path(filepath)
        self._shutdown_path = _resolve_path("data/shutdown.signal")
        self._last_mtime: float = 0.0
        self._listeners: list[Callable] = []
        self._on_shutdown: Optional[Callable] = None
        self._polling: bool = False

    def read_state(self) -> bool:
        """从 employee_state.json 加载状态到 AppState。"""
        with open(self._path, "r", encoding="utf-8") as f:
            data = json.load(f)
        state.load_from_dict(data)
        self._last_mtime = os.path.getmtime(self._path)

    def start_polling(self, interval=1.0, on_change=None, on_shutdown=None):
        """启动后台轮询线程。启动时自动清理上次残留的信号文件。"""
        if os.path.exists(self._shutdown_path):
            os.unlink(self._shutdown_path)
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

    def _poll_loop(self, interval: float):
        tick = 0.25  # 关闭信号检查粒度
        while self._polling:
            # 优先检测关闭信号
            if os.path.exists(self._shutdown_path):
                self._polling = False
                if self._on_shutdown:
                    self._on_shutdown()  # → _do_close()
                return

            # 检测状态变更
            if self.has_external_changes():
                self.read_state()
                for listener in self._listeners:
                    listener()  # → WorkbenchPage.refresh()

            time.sleep(tick)
```

### 主应用侧 (`persistence_service.py`)

```python
def save(self) -> bool:
    """保存状态时同步写入 employee_state.json 供员工读取。"""
    # ... filelock 保护写入 board_state.json ...
    from app.core.services.command_queue import write_employee_state
    write_employee_state()  # shutil.copy2(board_state.json → employee_state.json)
```

### 命令处理 (`command_queue.py`)

```
员工操作 → send_command() → pending_commands.json
                                │
主应用轮询(0.5s) → process_pending_commands()
  ├─ _execute_command(cmd)
  │    ├─ accept_task: validate → move_task("in_progress")
  │    ├─ block_task: validate → update_task(is_blocked=True) → move_task("parts_hold")
  │    └─ submit_task: validate → update_task(log, hours) → move_task("inspection")
  └─ 失败命令 _retries ≤ 3 保留重试，超过丢弃
```

## 联动关闭

### 设计原则

- **不杀进程**：不用 taskkill/os._exit/WM_CLOSE
- **不找窗口句柄**：PID 找不到 Flet 窗口（属于 fletd.exe）
- **不拦截关闭**：`prevent_close` 全部移除，走 Flet 原生快速通道
- **信号文件即 API**：员工提供 "关闭 API"——轮询检测到信号后自行 `close()`

### 关闭链路

```
主应用点 X
  │
  ├─ _close_window() / _on_window_close()
  │    └─ kill_employee_processes()
  │         └─ shutdown_employee_processes()
  │              ├─ write_shutdown_signal()          ← 写信号文件
  │              ├─ process_pending_commands()        ← flush 最后命令
  │              └─ return（不等员工响应）
  │
  └─ page.window.close()                             ← 主窗口原生关闭
                                                       
员工 StateSync [0.25s 轮询]
  │
  └─ 检测到 shutdown.signal
       └─ _do_close()
            ├─ stop_polling()                         ← 停后台轮询
            └─ page.window.close()                    ← 原生关闭自己
```

### 为什么 `close()` 在后台线程安全

`page.window.close()`（无 `prevent_close`）底层是 Windows 的 `PostMessage(hwnd, WM_CLOSE, 0, 0)`，这是 Windows API 保证的线程安全操作。StateSync 后台线程直接调不会导致 UI 异常。

### 信号残留清理

`StateSync.start_polling()` 启动时会自动删除上次残留的 `shutdown.signal`，防止下次启动误触发关闭。

## 乐观更新

员工操作后不等主应用响应，立即更新本地 state 并刷新 UI：

```python
def do_block(e):
    send_command("block_task", task.id, {"reason": reason})
    # 乐观更新：立即移动任务到阻塞列
    state.update_task(task.id, is_blocked=True, block_reason=reason)
    state.move_task(task.id, "parts_hold", changed_by=employee_name)
    close_ref.close()
    self.refresh()  # UI 即时响应
```

| 操作 | 乐观更新动作 |
|------|-------------|
| 接单 | `move_task("in_progress")` + 设 `planned_start` |
| 阻塞 | `update_task(is_blocked=True)` + `move_task("parts_hold")` |
| 提交验收 | `update_task(log, hours)` + `move_task("inspection")` |

若命令被主应用拒绝（校验失败），后台 `StateSync` 轮询(1s) 从权威数据源 `employee_state.json` 重新加载，自动纠正 UI。

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
| `app/employee/app.py` | 窗口应用：登录/工作台视图切换、窗口设置、关闭逻辑 |
| `app/employee/state_sync.py` | 状态同步器：employee_state.json 轮询 + 信号检测 |
| `app/employee/pages/login_page.py` | 登录页：员工搜索/选择 |
| `app/employee/pages/workbench_page.py` | 工作台页：任务列表 + 接单/阻塞/提交 + 乐观更新 |
| `app/core/services/command_queue.py` | IPC：命令队列 + employee_state 同步 + 信号文件 |
| `app/core/services/persistence_service.py` | 主应用持久化：filelock + write_employee_state() |
| `app/ui/pages/board_page.py` | 主应用：subprocess.Popen 启动 + 信号通知关闭 |
| `app/ui/app.py` | 主应用：轮询线程 + 关闭时联动清理 |

## 关键设计决策

1. **子进程而非线程**：员工窗口完全独立的 Python 进程，崩溃不影响主应用
2. **文件 IPC 而非 socket**：无需端口管理、防火墙配置，部署简单
3. **信号文件关闭而非杀进程**：避免 Flet 子进程(fletd.exe) 变孤儿，窗口残留
4. **乐观更新而非等待确认**：0ms 感知延迟，后台自动纠正
5. **移除 `prevent_close`**：走 Flet 原生快速关闭通道，`close()` 可在任意线程调用
