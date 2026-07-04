# TaskSense 重构计划

> 基于 2026-07-04 全面代码审查 | 目标：C → A- | 预计：6-8 天

---

## 总览

```
Phase 0: 快速止血（0.5天）→ 修复已知 Bug + 清理 print
Phase 1: 拆分 board_page.py（2天）→ 3538行 → ~300行协调者
Phase 2: 消除重复（1.5天）→ 提案/弹窗/AI命令统一
Phase 3: 架构加固（1.5天）→ 线程安全 + 依赖注入 + 配置统一
Phase 4: 清理收尾（1天）→ 代码规范 + 测试补充
```

---

## Phase 0：快速止血（0.5 天）

> 目标：修复影响用户使用的已知 Bug，不改变架构

### 0.0 立即处理：API Key 泄露 🔴🔴

**文件**：`settings.json`

**问题**：包含真实 DeepSeek API Key `sk-efd1c0e6269e42bb86a1a9ec7badd771`，已提交 git

**修复**：
1. 将 `settings.json` 中的 key 替换为 `"sk-your-key-here"`
2. 轮换 DeepSeek API Key（在平台重新生成）
3. 将 `settings.json` 添加到 `.gitignore`（或创建 `settings.example.json` 模板）
4. 从环境变量 `TASKSENSE_API_KEY` 加载真实 key

### 0.1 修复键盘处理器冲突 🔴

**文件**：`app.py`、`create_task_dialog.py`

**问题**：Dialog 打开时覆盖 `page.on_keyboard_event`，关闭时不恢复

**方案**：在 `app.py` 的 `on_kb` 中链式调用 `handle_ghost_keyboard`，不再让 Dialog 单独设置 handler

```python
# app.py - 唯一入口
def on_kb(e):
    if handle_ghost_keyboard(e):
        e.handled = True; return
    # ... 原有的 Ctrl+K, Esc 逻辑
```

删除 `create_task_dialog.py:37-38` 的 monkey-patch。

### 0.2 修复 `_poll_ghost_resolution` cancel=None 泄漏 🔴

**文件**：`board_page.py:594-616`

**问题**：`cancel` 为 None 时静默返回，不调用 `_finish_task_card`，任务注册表残留

**修复**：
```python
if cancel is None:
    self._finish_task_card(label, "已取消", theme.text_disabled)
    return
```

### 0.3 清理 80+ print 调试语句

**文件**：`board_page.py`、`agent_service.py`、`orchestrator.py`

**方案**：全部替换为 `log.debug(...)`（项目已有 `app/core/logging.py`）

```bash
# 替换模式
print(f"[CLASSIFY] ...")  →  log.debug("classify", ...)
print(f"[ACCEPTANCE] ...") →  log.debug("acceptance", ...)
print(f"[GHOST] ...")      →  log.debug("ghost", ...)
```

### 0.4 修复 `_reset_chat` 不检查 `_busy` 🟡

**文件**：`ai_chat.py:54-63`

**修复**：在方法开头添加 `if self._busy: return`

### 0.5 修复遗漏文件问题

| 文件 | 问题 | 修复 |
|------|------|------|
| `aircraft.py` | `to_dict()` 丢失 10+ 字段 | 补全序列化字段 |
| `loader.py` | `page_starts` off-by-1 | 修正偏移量计算 |
| `log_entry.py` | `LogType()` 无保护 | 添加 try/except |
| `requirements.txt` | UTF-16 编码 | 重新保存为 UTF-8 |
| `main.py` / `build_kb.py` | 重复的缓存检查 | 提取为 `app/knowledge/cache_utils.py` |

### 0.6 修复 `notification_bubble.py` 单例竞态

**文件**：`notification_bubble.py:35-37`

**修复**：将 `_active` 检查移入锁内

---

## Phase 1：拆分 board_page.py（2 天）

> 目标：3538 行上帝类 → ~300 行协调者 + 6 个专职模块

### 1.1 拆分前的准备

**步骤**：
1. 确保 222 个测试全部通过（基线）
2. 为 `BoardPage` 的关键方法补充测试（`_accept_ai_task`、`_reject_ai_task`、`_card_action`、`_force_clear_all_ghosts`）
3. 标记所有公开和私有方法

### 1.2 目标架构

```
app/ui/pages/board_page.py           (~300 行)
   ├── 仅保留：__init__, build, handle_keyboard
   └── 委托给以下模块：

app/ui/services/board_renderer.py    (~350 行)
   职责：看板数据渲染、幽灵卡注入、列级增量更新
   方法：
   - render_board(board_state, tasks_map) 
   - render_ghost_cards(ai_tasks)
   - add_single_ghost(task)
   - refresh_incremental(board_state, tasks_map)
   - get_ghost_prop_type(task) → (prop_type, render_column)  # 消除重复

app/ui/services/proposal_handler.py  (~200 行)
   职责：统一所有幽灵卡接受/拒绝逻辑（消除三重冗余）
   方法：
   - accept(proposal) → ProposalResult
   - reject(proposal) → ProposalResult
   - accept_all() → list[ProposalResult]
   - reject_all() → list[ProposalResult]
   - sync_to_chat_panel(ai_chat, result)

app/ui/services/dialog_manager.py    (~1200 行，从 board_page 移出)
   职责：所有弹窗的构建和生命周期
   类：
   - DialogBuilder (header/footer/button 工厂)
   - PriorityDialog
   - ScheduleDialog
   - SubmitDialog
   - BlockDialog
   - EditTaskDialog
   - FilterDialog
   工厂方法（消除 ~240 行重复）：
   - DialogBuilder.header(icon, title, on_close) → ft.Container
   - DialogBuilder.footer(buttons) → ft.Container
   - DialogBuilder.button_style() → ft.ButtonStyle

app/ui/services/ai_command_handler.py (~700 行，从 board_page 移出)
   职责：7 个 AI 命令的统一执行
   类：
   - AICommandRunner (装饰器/基类)
   - OutlineCommand
   - GenTasksCommand
   - ClassifyCommand
   - ScheduleCommand
   - AcceptanceCommand
   - ReportCommand
   - ReviewCommand
   共享模式（消除 ~280 行重复）：
   - _prepare(task_label, session_id) → cancel_event
   - _run_in_thread(fn, cancel_event)
   - _finish(label, status, color)

app/ui/services/cancel_coordinator.py (~200 行，从 board_page 移出)
   职责：取消流程统一处理
   方法：
   - cancel_task(task_id, task_type)
   - force_clear_ghosts(task_id=None)
   - reject_all_proposals(task_id=None)
   - cleanup_ui(ai_chat, status_bar)

app/ui/services/task_registry.py     (~150 行，从 board_page 移出)
   职责：任务注册表（线程安全）
   方法：
   - register(task_id, label, status, task_type, progress)
   - unregister(task_id)
   - update_status(task_id, status, progress)
   - get_all() → list[TaskEntry]
```

### 1.3 拆分步骤

**第 1 步（0.5天）**：提取 `DialogManager`
- 创建 `app/ui/services/dialog_manager.py`
- 将 6 个 `_dlg_*` 方法移入
- 提取 `DialogBuilder` 工厂
- `board_page` 委托调用

**第 2 步（0.5天）**：提取 `ProposalHandler` + `BoardRenderer`
- 创建 `proposal_handler.py`
- 统一 `accept`/`reject` 逻辑
- 修改 `board_page` 和 `ai_chat.py` 都通过 Handler 操作
- 创建 `board_renderer.py`
- 统一幽灵卡类型判断

**第 3 步（0.5天）**：提取 `AICommandHandler` + `CancelCoordinator`
- 创建 `ai_command_handler.py`
- 使用模板方法模式消除 7 处线程样板
- 创建 `cancel_coordinator.py`

**第 4 步（0.5天）**：提取 `TaskRegistry` + 收尾
- 创建 `task_registry.py`（加锁）
- `board_page` 精简为协调者
- 运行全部测试确认无回归

### 1.4 每个步骤的验证

每完成一个步骤：
```bash
python -m pytest tests/ -v  # 确保 222 个测试仍然通过
python main.py              # 手动冒烟测试
```

---

## Phase 2：消除重复（1.5 天）

### 2.1 统一 agent_service.py 右键菜单方法

**文件**：`agent_service.py:565-653`

5 个方法（`explain_task`、`search_docs`、`classify_single`、`schedule_single`、`review_single`）几乎完全相同。

**方案**：提取通用方法
```python
@staticmethod
def _run_single_task_ai(prompt_file: str, task_info: dict, 
                        session_prefix: str, cancel_event=None) -> str:
    """所有右键菜单 AI 工具的统一入口。"""
    if not llm.is_available:
        return "[Error] LLM 不可用"
    prompt = _load_prompt(prompt_file)
    user_msg = "\n".join(f"- {k}: {v}" for k, v in task_info.items())
    return agent.ask(f"{prompt}\n\n## Task Details\n{user_msg}",
                     session_id=f"{session_prefix}_{task_info.get('id','')}",
                     cancel_event=cancel_event, timeout=15.0)
```

### 2.2 合并 settings.py 和 settings_manager.py

**文件**：`config/settings.py`、`config/settings_manager.py`

**方案**：
- 删除 `settings.py`（dataclass 版本）
- 将 `settings_manager.py` 扩展为唯一配置源
- 统一默认值（特别是 `embedding_model` 字段）
- 在 `settings_manager.py` 中添加 `from_env()` 支持

### 2.3 ToolExecutor 注册表化

**文件**：`agent/orchestrator.py:40-80`

20+ 分支 if-elif 链 → 字典分发：
```python
TOOL_HANDLERS: dict[str, Callable] = {
    "search_knowledge_base": lambda p: ToolExecutor._search_kb(p),
    "lookup_ata_chapter": lambda p: ToolExecutor._lookup_ata(p),
    # ... 从 lazy import 改成模块级注册
}
```

### 2.4 提取 ATA 关键词字典

**文件**：`agent/orchestrator.py:432-517`（90 行硬编码 dict）

→ 移到 `app/config/ata_keywords.py` 作为数据文件

### 2.5 提取 JSON 解析为独立工具

**文件**：`agent_service.py:471-558`（`_review_one_batch` 的 4 级 JSON 解析）

→ 移到 `app/agent/json_extractor.py`

---

## Phase 3：架构加固（1.5 天）

### 3.1 线程安全修复

**文件**：`board_page.py`（拆分后 → `task_registry.py`）

| 问题 | 修复 |
|------|------|
| `_task_registry` 无锁 | 添加 `threading.Lock` |
| `_report_result` / `_review_result` 无锁 | 添加锁或改用 `threading.Event` |
| 后台线程直接调 `.update()` | 替换为 `page.run_task(lambda: ...)` |
| `LogService` 每条日志创建线程 | 改用 debounce timer（参考 PersistenceService） |
| `PersistenceService` 事件订阅泄漏 | 添加 `unsubscribe` 逻辑 |
| Logging 模块 `_indent` 无锁 | 加锁或使用 `threading.local` |

### 3.2 解决循环导入

当前 20+ 处内联导入表明循环依赖。拆分 `board_page.py` 后大部分自然解决。

剩余的：
- `state.py → log_service.py → state.py`：通过事件总线解耦（logging 作为 event_bus 订阅者）
- `tools/* → state.py → tools/*`：已设计的依赖方向合理（工具 → state）

### 3.3 统一配置系统

- 删除 `settings.py`
- `settings_manager.py` 成为唯一入口
- 添加 `from_env()` 方法（移植自 `settings.py`）

### 3.4 依赖注入（可选，如时间允许）

将全局单例改为构造函数注入：
```python
class BoardPage:
    def __init__(self, 
                 state: AppState,
                 task_service: TaskService,
                 board_service: BoardService,
                 agent: AgentOrchestrator,
                 board_renderer: BoardRenderer,
                 proposal_handler: ProposalHandler,
                 dialog_manager: DialogManager,
                 ai_command_handler: AICommandHandler,
                 cancel_coordinator: CancelCoordinator,
                 task_registry: TaskRegistry):
```

### 3.5 修复 SettingsWindow 单例状态

**文件**：`settings_window.py`

将全部类变量改为实例变量，避免二次打开破坏状态。

---

## Phase 4：清理收尾（1 天）

### 4.1 代码规范

- 统一 `import` 位置（清除所有方法体内 `import`）
- 修复 `chat_bubble.py` 中 `_reflash` → `_refresh` 拼写
- `md_renderer.py` 中 `parse_markdown_to_spans` 拆分为子函数（200 行 → 多个 30-50 行函数）
- 删除 `board_controller.py` 中 `load_demo_data()`（移到 `scripts/`）

### 4.2 测试补充

优先补充：
1. `ProposalHandler` 测试（accept/reject 各类型）
2. `CancelCoordinator` 测试（单任务/批量清除）
3. `TaskRegistry` 线程安全测试
4. `BoardRenderer` 幽灵卡类型判断测试

### 4.3 删除死代码

- `board_page.py` 中 `_run_agent_cmd`（行1901-1912，未被调用）
- `board_page.py` 中 `_start_ghost_polling`（行2612-2634，功能与 `_poll_ghost_resolution` 重复）
- `board_controller.py` 中 `moves` 变量（行263-267，未使用的列表）
- `ai_suggestion.py` 中 `AISuggestionPanel`（占位符）

### 4.4 性能优化

- `BoardState.task_column`：添加反向索引 `task_id → col_id`（O(n*m) → O(1)）
- `BoardService.search_tasks`：考虑添加缓存索引
- `chat_bubble.py` 中 `_char_w` 的宽度估算考虑使用 Flet 的实际测量

---

## 完整文件变更清单

### 新增文件

| 文件 | 来源 | 估行数 |
|------|------|--------|
| `app/ui/services/board_renderer.py` | 从 board_page 提取 | ~350 |
| `app/ui/services/proposal_handler.py` | 新建（统一三重冗余） | ~200 |
| `app/ui/services/dialog_manager.py` | 从 board_page 提取 | ~1200 |
| `app/ui/services/ai_command_handler.py` | 从 board_page 提取 | ~700 |
| `app/ui/services/cancel_coordinator.py` | 从 board_page 提取 | ~200 |
| `app/ui/services/task_registry.py` | 从 board_page 提取 | ~150 |
| `app/config/ata_keywords.py` | 从 orchestrator 提取 | ~100 |
| `app/agent/json_extractor.py` | 从 agent_service 提取 | ~80 |

### 修改文件

| 文件 | 变更 |
|------|------|
| `app/ui/pages/board_page.py` | **3538 → ~300 行**（协调者） |
| `app/ui/components/ai_chat.py` | 删除提案逻辑，改用 ProposalHandler |
| `app/ui/services/agent_service.py` | 提取 JSON 解析 + 统一右键方法 |
| `app/agent/orchestrator.py` | ToolExecutor 注册表 + 删除 ATA 字典 |
| `app/ui/app.py` | 修复键盘冲突 |
| `app/core/services/log_service.py` | debounce 替代 per-call 线程 |
| `app/core/services/persistence_service.py` | 修复事件订阅泄漏 |
| `app/ui/widgets/notification_bubble.py` | 修复单例竞态 |
| `app/ui/components/create_task_dialog.py` | 删除键盘 handler monkey-patch |
| `app/ui/widgets/ghost_text.py` | weakref 替代 list 防止泄漏 |
| `app/ui/pages/settings_window.py` | 类变量 → 实例变量 |
| `app/config/settings_manager.py` | 合并 settings.py |
| `app/core/logging.py` | indent 锁 |
| `app/core/models/task.py` | 添加 `to_submission_context()` |

### 删除文件

| 文件 | 原因 |
|------|------|
| `app/config/settings.py` | 与 settings_manager 合并 |

### 删除代码片段

| 位置 | 内容 | 理由 |
|------|------|------|
| `board_controller.py:175-269` | `load_demo_data()` | 移到 scripts/ |
| `board_page.py:1901-1912` | `_run_agent_cmd` | 死代码 |
| `board_page.py:2612-2634` | `_start_ghost_polling` | 与 _poll_ghost_resolution 重复 |
| `ai_suggestion.py:56-73` | `AISuggestionPanel` | 占位符 |
| `orchestrator.py:432-517` | `_guess_ata` 字典 | 移到 ata_keywords.py |

---

## 里程碑 & 验收标准

| 里程碑 | 验收标准 |
|--------|---------|
| Phase 0 完成 | 键盘冲突修复 + 80+ print 清理 + 3 个 Bug 修复，222 测试通过 |
| Phase 1 完成 | board_page.py ≤ 500 行，6 个新模块全部可用，222 测试通过 |
| Phase 2 完成 | 提案逻辑单一路径，弹窗工厂可用，ToolExecutor 注册表化 |
| Phase 3 完成 | 无锁共享状态全部加固，配置系统统一 |
| Phase 4 完成 | 0 处方法内 import，测试覆盖新增模块 |

---

## 风险 & 回滚策略

- **每个 Phase 结束后提交**，不跨 Phase 混合变更
- Phase 1 风险最高——建议先在分支上进行
- 如果 Phase 1 拆分导致回归，可以按模块逐个回滚（因为是独立文件）
- 关键验收：每次拆分后手动冒烟测试（创建任务、拖放、AI 工具、右键菜单）
