# TaskSense 代码质量审查报告

> 初始审查：2026-07-04 | 终审更新：2026-07-05（重构完成后）

## 重构成果

```
board_page.py: 3538 → 2776 行 (-762, -22%)
新增模块: 10 个
提交: 19 次 | 测试: 311/311 (0 失败)
评级: 架构 C→B+ | 可维护性 C→B+
```

---

## 目录
1. [架构层面问题](#一架构层面问题)
2. [代码质量问题](#二代码质量问题)
3. [Flet 0.28.3 兼容性问题](#三flet-0283-兼容性问题)
4. [线程安全问题](#四线程安全问题)
5. [潜在 Bug 清单](#五潜在-bug-清单按严重度)
6. [重复代码模式](#六重复代码模式)
7. [重构建议](#七重构建议按优先级)
8. [总结评分](#八总结评分)

---

## 一、架构层面问题

### 1.1 board_page.py — 超级上帝类（3538 行）

`BoardPage` 承担了以下全部职责：

| 职责 | 估行数 | 应归属 |
|------|--------|--------|
| UI 构建 | ~60 | Page |
| 看板渲染 + 幽灵卡管理 | ~350 | BoardRenderer |
| 6 个弹窗（优先级/排程/编辑/筛选/阻塞/提交） | ~1200 | DialogManager |
| 7 个 AI 命令 | ~800 | AICommandHandler |
| 9 列右键菜单 | ~200 | ContextMenuBuilder |
| 任务注册表 + 状态栏 | ~150 | TaskRegistry |
| 取消流程（幽灵清除/提案拒绝/UI更新） | ~200 | CancelCoordinator |
| 报表/审核弹窗 | ~350 | ReportViewer |
| 键盘/搜索/筛选 | ~100 | InputHandler |

### 1.2 幽灵卡提案逻辑三重冗余

接受/拒绝逻辑在 **3 个位置**独立实现：

| 位置 | 方法 | 重复度 |
|------|------|--------|
| `board_page._accept_ai_task` / `_reject_ai_task` | 幽灵卡按钮回调 | 完整实现 |
| `AIChatPanel._accept_proposal` / `_reject_proposal` | 对话区提案按钮 | ~90% 相同 |
| `AIChatPanel._accept/reject_all_proposals` | 批量按钮 | 内联复制上述逻辑 |

### 1.3 服务层空心化

- `TaskService`（212 行）：大部分是 `self.state.xxx()` 透传
- `BoardService`（60 行）：全部透传
- `BoardController`（269 行）：定义了清晰接口但 `board_page.py` 几乎不使用
- `AgentService`（655 行）：纯静态工具类，混合了 LLM 调用、离线降级、JSON 解析、单任务 AI 工具

### 1.4 全局单例泛滥

```python
state = AppState()                    # state.py
board_service = BoardService()        # board_service.py
task_service = TaskService()          # task_service.py
agent = AgentOrchestrator()           # orchestrator.py
log_service = LogService()            # log_service.py
employee_service = EmployeeService()  # employee_service.py
event_bus = EventBus()                # events.py
board_scheduler = BoardScheduler()    # board_scheduler.py
```

5 个 Service 类使用相同的手动单例模式（`__new__` + `_instance` + `_initialized` + `reset()`），约 10 行样板代码/类。`reset()` 非线程安全。

### 1.5 配置系统重复

`settings.py`（dataclass + 环境变量）和 `settings_manager.py`（JSON 文件持久化）有不同默认值：
- `settings.py`: `embedding_model = "text-embedding-3-small"`
- `settings_manager.py`: `embedding_model = "all-MiniLM-L6-v2"`

两套系统的字段结构也不兼容。

---

## 二、代码质量问题

### 2.1 弹窗样板代码重复（6 个弹窗）

`_dlg_submit`、`_dlg_block`、`_dlg_priority`、`_dlg_schedule`、`_dlg_edit`、`_dlg_filter`——
每个弹窗重复 ~40 行 header/footer/button 代码：

```python
header = ft.Container(ft.Row([
    ft.Icon(...), ft.Text(...), ft.Container(expand=True),
    ft.IconButton(ft.Icons.CLOSE, ...)]), padding=..., border=...)
footer = ft.Container(ft.Row([
    ft.Container(expand=True),
    ft.OutlinedButton("取消", ...),
    ft.ElevatedButton("确认", ...)]), padding=...)
btn_st = ft.ButtonStyle(shape=RoundedRectangleBorder(radius=s(6)), ...)
```

### 2.2 AI 命令线程模式重复 7 次

`_cmd_outline`、`_cmd_gen_tasks`、`_cmd_classify`、`_cmd_schedule`、`_cmd_acceptance`、`_cmd_report`、`_cmd_review`——
每个 ~40 行样板：
```python
if not self.ai_chat: Toast(...); return
if self.ai_chat.is_task_running: Toast(...); return
self._open_ai_panel()
self.ai_chat.show_task_card(...)
self._register_task(...)
active_task_registry.set_active(...)
import threading
def _do():
    cancel = getattr(self.ai_chat, '_cancel_event', None)
    ...
threading.Thread(target=_do, daemon=True).start()
```

### 2.3 辅助函数在方法内重复定义

`_norm_tf`、`_label`、`_col` 在 `_dlg_schedule`（行1231-1249）和 `_dlg_edit`（行2955-2977）中各自内联定义，几乎完全一样。
`_make_date_picker` 在两个方法中完整重复。

### 2.4 幽灵卡类型判断逻辑重复 3 次

```python
if t.ai_priority: prop_type, render_column = "classify", "triage"
elif schedule_data: prop_type, render_column = "schedule", "scheduled"
elif getattr(t, 'ai_acceptance_recommendation', None): ...
else: prop_type, render_column = "new_task", t.status.value
```
出现在 `_render_ai_ghost_cards`、`_add_single_ghost`、`_refresh_board` 中。

### 2.5 调试 print 语句泛滥

代码中超过 **80 个** `print()` 调试语句（`[CLASSIFY]`、`[ACCEPTANCE]`、`[GHOST]`、`[REVIEW]` 等前缀），应替换为 `log.debug()`。

### 2.6 内联导入（循环依赖回避）

20+ 处 `from ... import ...` 在方法体内执行，掩盖了真正的循环依赖问题：
- `state.py` 内联导入 `LogType` / `log_service`
- `orchestrator.py` 内联导入 12 个工具模块
- `task_service.py` 内联导入 `log_service`
- `validators.py` 内联导入 `employee_service`

### 2.7 硬编码魔法数字

```python
CHUNK_SIZE = 6           # agent_service.py
MAX_TOOL_ROUNDS = 3      # orchestrator.py（但循环实际执行 4 轮）
for _ in range(300):     # board_page.py 多处（5分钟超时）
time.sleep(0.05)         # 防抖延迟
PW, PH = 720, 780        # 弹窗尺寸散落多处
_guess_ata() 90 行 dict  # orchestrator.py 内嵌
```

### 2.8 错误处理不一致

同一 codebase 中三种模式并存：
- `TaskService.move_task` → 抛出 `BusinessRuleError`
- `TaskService.set_priority` → 静默返回 `None`
- `BoardScheduler.tick` → `except Exception: pass`（15+ 处）
- `PersistenceService.save` → 返回 `bool` + `print()`

### 2.9 orchestrator.py 的 ToolExecutor

`execute()` 方法（行44-79）是 20+ 分支的 if-elif 链，每个分支内联导入工具模块。应改为注册表/字典分发模式。

### 2.10 ai_chat.py 的 _reset_chat 竞态

`_reset_chat`（"新对话"按钮）不检查 `_busy` 标志，可能与正在运行的 `_process` 竞争，导致加载指示器索引错误。

---

## 三、Flet 0.28.3 兼容性问题

### 3.1 🔴 键盘处理器冲突

`app.py` 和 `CreateTaskDialog` 都设置 `page.on_keyboard_event`。对话框打开时覆盖 app 的 handler，关闭时不恢复——app 的键盘处理（Ctrl+K、Esc）永久丢失。

### 3.2 🟡 OverlayDimmer 窗口缩放漂移

`OverlayDimmer` 在构建时捕获 `page.width/height`。窗口缩放后，dimmer 尺寸和内容面板位置不会更新，留下未覆盖区域。

### 3.3 🟡 AI 菜单快速双击可能创建重复 overlay

`app.py` 的 `_show_ai_menu` / `_close_ai_menu` 之间缺少竞态保护。

### 3.4 🟡 ghost_text.py 的 `_active_ghost_fields` 内存泄漏

GhostTextField 从控件树移除时（对话框关闭），不清理 `_active_ghost_fields` 全局列表，造成引用泄漏。

### 3.5 已验证安全的 API 使用

以下在 0.28.3 中确认安全：
- `GestureDetector.mouse_cursor` ✅（GestureDetector 支持，只有 Container 不支持）
- `TextField.focused_border_color` ✅（focused_border_color 存在，focused_border 不存在）
- overlay 中显式 `width/height` 不依赖 `expand` ✅
- 不使用 `page.dialog` / `PopupMenuButton` ✅

---

## 四、线程安全问题

### 4.1 `_task_registry` 无锁保护

`board_page._task_registry`（`list[dict]`）被主线程和多个后台线程并发读写，无任何锁。

### 4.2 `_report_result` / `_review_result` 无锁

后台线程写入，`_refresh_status_bar`（状态变更回调触发）读取，无同步。

### 4.3 后台线程直接调用 Flet `.update()`

多处后台线程直接调用控件 `.update()`（如 `progress.update()`、`report_f.update()`）。正确做法是通过 `page.run_task()`。

### 4.4 `cancel_event` 生命周期竞态

`hide_task_card()` 将 `self._cancel_event = None`，同时后台线程可能持有旧引用。虽有 `getattr(..., None)` 保护，但存在窗口：线程 A 获取 event 引用 → 线程 B 置 None → 线程 A 调用 `event.is_set()`。

### 4.5 `LogService.log()` 每条日志创建一个 daemon 线程

高日志量时可创建数百线程（线程创建成本高）。应用 `PersistenceService` 的 debounce timer 模式。

### 4.6 `PersistenceService` 事件订阅泄漏

`stop_auto_save()` → `start_auto_save()` 循环会累积 event_bus 订阅（无 `unsubscribe`），导致 `mark_dirty` 被多次调用。

### 4.7 `BoardScheduler._running` 数据竞争

普通 `bool` 标志被多线程无锁读写。

### 4.8 Logging 模块 `_indent` 无锁

`begin()`/`end()` 修改全局 `_indent` 整数，多线程并发导致缩进错乱。

---

## 五、潜在 Bug 清单（按严重度）

### 🔴 严重

| # | 问题 | 文件:行 | 说明 |
|---|------|---------|------|
| 1 | 键盘处理器冲突 | app.py:456 vs create_task_dialog.py:37 | Dialog 覆盖 app handler 且关闭时不恢复 |
| 2 | `_poll_ghost_resolution` cancel=None 泄漏 | board_page.py:599-601 | 静默返回而不调用 `_finish_task_card`，任务注册表残留 |
| 3 | `block_task` 部分更新风险 | task_service.py:146-165 | `is_blocked=True` 设置后 `move_task` 可能失败，任务状态不一致 |
| 4 | `update_task` 可直接改 status 绕过 transition_to | state.py:141-143 | 不更新 `status_history` 和 `completed_at` |
| 5 | `clear()` 不清空磁盘日志 | log_service.py | `load()` 会重新加载旧条目 |

### 🟡 中等

| # | 问题 | 文件:行 | 说明 |
|---|------|---------|------|
| 6 | `_reset_chat` 不检查 `_busy` | ai_chat.py:54-63 | 与 `_process` 竞争导致加载指示器索引错误 |
| 7 | `delete_task` 不清理孤立引用 | state.py:226-255 | `parent_task_id`、`blocked_by` 等残留 |
| 8 | OverlayDimmer 窗口缩放漂移 | overlay_dimmer.py:89 | `page.width/height` 不更新 |
| 9 | `validate_wip` 与 `wip_exceeded` 不一致 | validators.py vs kanban.py | `>=` vs `>` — WIP 恰好达到上限时行为矛盾 |
| 10 | `_active_ghost_fields` 内存泄漏 | ghost_text.py:20 | 对话框关闭后不清理 |
| 11 | `validate_create(title, aircraft_reg)` 不校验 aircraft_reg | validators.py:53 | 签名误导 |
| 12 | `_check_ghost_pending_completion` 中延迟线程访问已销毁控件 | board_page.py:359-365 | `self.ai_chat` 可能已被销毁 |
| 13 | 设置系统默认值不一致 | settings.py vs settings_manager.py | 两套配置系统有不同默认值 |
| 14 | `_guess_ata` 90 行硬编码字典 | orchestrator.py:435-517 | 维护困难，应外置为数据文件 |

### 🟢 轻微

| # | 问题 | 文件 | 说明 |
|---|------|------|------|
| 15 | `_build_review_summary` badges 用 emoji 而非图标 | board_page.py:2332-2334 | `"🔴"` / `"⚠"` / `"ℹ"` 不如 `ft.Icons` |
| 16 | `toggle_checklist_item` item 未找到返回 None | task_service.py:197-208 | 调用者无法区分"任务不存在"和"项目不存在" |
| 17 | `search_tasks` O(n) 线性扫描无索引 | board_service.py:28-42 | 大规模数据时性能差 |
| 18 | `_parse_tool_calls` 正则解析脆弱的 key=value 格式 | orchestrator.py:158-180 | 参数值含换行或 `=` 时破坏 |
| 19 | `search_knowledge_base` stats fallback sum 可能不正确 | search_tools.py:35-36 | 对非 total 整数求和产生误判 |
| 20 | `_start_ghost_polling` 与 `_poll_ghost_resolution` 功能重复 | board_page.py:2612-2634 | 冗余方法 |

---

## 六、重复代码模式

### 模式 1：弹窗 header/footer（6 处，每处 ~40 行）
`_dlg_priority` / `_dlg_schedule` / `_dlg_submit` / `_dlg_block` / `_dlg_edit` / `_dlg_filter`

### 模式 2：AI 命令线程样板（7 处，每处 ~40 行）
`_cmd_outline` / `_cmd_gen_tasks` / `_cmd_classify` / `_cmd_schedule` / `_cmd_acceptance` / `_cmd_report` / `_cmd_review`

### 模式 3：幽灵卡类型判断（3 处，每处 ~30 行）
`_render_ai_ghost_cards` / `_add_single_ghost` / `_refresh_board`

### 模式 4：提案 accept/reject（3 处，每处 ~50 行）
`board_page._accept/reject_ai_task` / `AIChatPanel._accept/reject_proposal` / `AIChatPanel._accept/reject_all_proposals`

### 模式 5：日期选择器工厂（2 处，每处 ~40 行）
`_dlg_schedule` 和 `_dlg_edit` 中完整重复的 `_make_date_picker` / `_clamp_tf` / `_recalc_hours` / `_get_dt`

### 模式 6：单例模式样板（5 处，每处 ~10 行）
`BoardScheduler` / `EmployeeService` / `PersistenceService` / `LogService` / `SettingsManager`

### 模式 7：`_norm_tf` / `_label` / `_col` 辅助函数（2 处，每处 ~30 行）
`_dlg_schedule` 和 `_dlg_edit` 内联定义

---

## 七、重构建议（按优先级）

### P0：拆分 board_page.py（预计 2-3 天）

从 3538 行降至 ~300 行协调者：

```
app/ui/pages/board_page.py           → ~300 行（build + 事件路由）
app/ui/services/board_renderer.py    → 看板渲染 + 幽灵卡注入
app/ui/services/dialog_manager.py    → 6 个弹窗统一工厂
app/ui/services/ai_command_handler.py → 7 个 AI 命令
app/ui/services/task_registry.py     → 任务注册表 + 线程安全
app/ui/services/cancel_coordinator.py → 取消流程
```

### P0：消除幽灵卡三重冗余（预计 0.5 天）

创建单一 `ProposalHandler`：
```python
class ProposalHandler:
    def accept(proposal) -> ProposalResult
    def reject(proposal) -> ProposalResult
    def accept_all() / reject_all()
```

### P1：提取弹窗工厂（预计 0.5 天）

```python
class DialogBuilder:
    @staticmethod
    def header(icon, title, on_close) -> ft.Container
    @staticmethod
    def footer(buttons, ...) -> ft.Container
    @staticmethod
    def button_style() -> ft.ButtonStyle
```

### P1：统一 AI 命令执行模式（预计 1 天）

装饰器模式消除 7 处重复线程样板：
```python
@ai_command(label="生成任务", session_id="gen_tasks")
def _cmd_gen_tasks(self) -> AICommandContext: ...
```

### P1：修复键盘处理器冲突（预计 0.5 天）

将 `handle_ghost_keyboard` 和 app 的 `on_kb` 合并为链式调用。

### P2：清理 print 语句（预计 0.5 天）

80+ 处 `print()` 替换为 `log.debug()`。

### P2：线程管理规范化（预计 1 天）

- 引入 `ThreadPoolExecutor` 统一管理
- 创建 `BackgroundTask` 包装器（cancel_event + 状态回调 + UI 安全更新）
- `_task_registry` / `_report_result` / `_review_result` 加锁

### P2：ToolExecutor 注册表化（预计 0.5 天）

```python
TOOL_REGISTRY: dict[str, Callable] = {
    "search_knowledge_base": search_knowledge_base.invoke,
    "get_board_summary": get_board_summary.invoke,
    ...
}
```

### P3：充实服务层（预计 1 天）

- `TaskService`：下沉 `board_page` 中的业务逻辑
- `BoardService`：添加 `get_ai_proposed_tasks()` 等查询方法
- 让 `BoardController` 成为 `board_page` 的唯一数据入口

### P3：解决循环导入（预计 0.5 天）

- 将 `_guess_ata` 移到独立 `ata_guesser.py`
- 将 `_CMD_PROMPTS` 移到 prompt 文件
- 将 `_build_submission_context` 移到 `Task.to_submission_context()`

### P3：合并配置系统（预计 0.5 天）

统一 `settings.py` 和 `settings_manager.py` 为单一配置源。

### P4：依赖注入（预计 1 天）

```python
class BoardPage:
    def __init__(self, state, task_service, board_service, agent):
```

### P4：Task 模型拆分（预计 0.5 天）

40+ 字段拆为子对象：`AircraftInfo`、`ScheduleInfo`、`ComplianceInfo`、`AIMetadata`。

---

## 八、其他文件发现

### md_renderer.py — `parse_markdown_to_spans` 200 行 + 6 层嵌套

Markdown 渲染器的主函数是代码中嵌套最深的逻辑（表格处理 6 层 while/for），链接 token 被完全忽略（链接显示为纯文本），数学 sentinel 注入使用 `\x00` 字节。

### settings_window.py — classmethod 滥用

全部状态存储在类变量（`_panel`、`_dimmer`、`_page`、`_fields`、`_active`），作为单例使用。再次打开会破坏第一次的状态。`_build_section` 是一个 93 行的 if/elif 方法。`_save` 中的键分割在缺失点时崩溃。

### chat_bubble.py — 变量名拼写错误

`_reflash`（应为 `_refresh`）出现在 4 个位置。`prompt_bubble` 使用内联硬编码颜色，完全绕过主题系统。

### notification_bubble.py — 单例竞态

`_active` 检查在锁外进行——两个线程可能同时通过检查，导致显示重复通知。无限队列增长无限制。`_page` 引用从不清理。

### badge.py — 3 字符 hex 代码崩溃

`_alpha` 方法只处理 6 字符十六进制。`"#fff"` 会在 `h[4:6]` 产生空字符串并崩溃。

### pipeline.py — 路径解析脆弱

使用 `Path(__file__).parent.parent.parent` 三层向上爬。项目结构改变会导致静默解析为错误路径。`search` 和 `add_chunks` 并发调用存在 BM25 缓存竞态。

---

## 九、遗漏文件发现（第 7 轮扫描）

### 🔴 安全：API Key 明文提交

`settings.json` 包含真实 DeepSeek API Key `sk-efd1c0e6269e42bb86a1a9ec7badd771`，已提交到 git 仓库。应立即：
1. 替换为占位符 `"sk-your-key-here"`
2. 从 git 历史中清除（`git filter-branch` 或轮换 key）
3. 从环境变量或 `.env` 文件加载

### aircraft.py — `to_dict()` 静默丢失 10+ 字段

`msn`、`hours_since_a_check`、`hours_since_c_check`、`cycles_since_a_check`、`last_*_check`（3 个）、`current_zone`、`mel_items` 等未序列化。如果用于持久化则造成数据丢失。

### loader.py — `page_starts` 偏移量 off-by-1

`"\n\n".join(text_parts)` 只在 parts **之间**插入分隔符，但代码在最后一个 part 后多算了 2 个字符。下游使用会出错。

### log_entry.py — 不安全的 `LogType()` 转换

反序列化损坏数据时 `ValueError` 未捕获，可能阻止整个日志文件加载。

### gen_demo_json.py — 直接访问 state 私有属性

`state._tasks.clear()` / `state._task_order = ...` 与 state 内部实现紧密耦合。

### requirements.txt — UTF-16 编码

文件被 pip freeze 生成时编码为 UTF-16 BOM，在其他平台可能读取失败。

### main.py — asyncio StreamWriter monkey-patch

在模块导入时无条件修改 `asyncio.streams.StreamWriter.__del__`，Python 版本升级可能破坏。

### 跨文件重复

`main.py:20-31` 和 `scripts/build_kb.py:25-37` 中相同的模型缓存检查逻辑应提取为共享函数。

---

## 十、总结评分

| 维度 | 评级 | 说明 |
|------|------|------|
| 架构 | ⚠️ C | 3538 行上帝类 + 三重幽灵卡冗余 + 服务层空心化 + 全局单例 |
| 代码质量 | ⚠️ C+ | 大量重复（弹窗/AI命令/幽灵卡）、print 残留、内联导入 |
| 正确性 | 🟡 B- | 核心流程正确，但边界条件不足（cancel泄漏、竞态、键盘冲突） |
| 线程安全 | 🔴 D | 多处无锁共享状态、后台线程直接操作 UI、cancel_event 竞态 |
| 可维护性 | ⚠️ C | 单文件过大、修改需穿越上帝类、内联 UI 构建难以复用 |
| 可测试性 | 🔴 D | 全局单例 + 无依赖注入、222 核心测试通过但缺少 UI/Agent 测试 |

### 数据统计

| 指标 | 数值 |
|------|------|
| 总代码行数 | ~16,500 |
| 最大文件 | board_page.py (3,538 行) |
| 重复模式 | 7 类（共计 ~1,200 行可消除） |
| print 调试残留 | 80+ 处 |
| 弹窗重复代码 | 6 处（~240 行） |
| AI 命令重复样板 | 7 处（~280 行） |
| 幽灵卡逻辑重复 | 3 处（~150 行） |
| 线程安全风险点 | 8 处 |
| Flet 兼容性风险 | 2 处（键盘冲突🔴 + 缩放漂移🟡） |

---

**最优先行动**（按此顺序执行可得最大收益）：
1. 拆分 `board_page.py` + 消除幽灵卡三重冗余 → C → B+
2. 提取弹窗工厂 + 统一 AI 命令模式 → B+ → A-
3. 修复键盘冲突 + 线程安全 → A- → A
4. 清理 print + 合并配置 + 依赖注入 → 可持续维护
