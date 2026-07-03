# Task Lock Protocol — Agent 任务锁协议

最后更新：2026-07-03

## 概述

防止 AI Agent 在执行工具任务期间被用户聊天消息带偏，确保 Agent 始终专注于当前任务直到完成。

### 问题场景

1. 用户点击菜单启动"自动分类"工具
2. 工具在后台调用 Agent，Agent 正在逐个分类任务
3. 用户在聊天框输入"帮我查一下 ATA 32"
4. ~~Agent 跑去查 ATA 32，分类任务脱离监管~~
5. **修复后**：Agent 拒绝偏离，回复"我正在执行自动分类任务，完成后立即为您处理"

---

## 架构

```
┌─────────────────────────────────────────────────┐
│                 board_page.py                    │
│  _cmd_classify / _cmd_outline / ...              │
│    │                                              │
│    ├─ set_active(session_id, label, phase)       │
│    ├─ AgentService.ask(prompt, session_id)       │
│    └─ 完成/取消 → _finish_task_card → clear()    │
└──────────────────┬──────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────┐
│            orchestrator.ask()                    │
│    │                                              │
│    ├─ inject_context(question, session_id)       │
│    │   ├─ 同 session → 跳过注入                   │
│    │   └─ 不同 session → 前缀 task_guard.md       │
│    │                                              │
│    └─ _agent_loop(conv, llm_client)              │
└──────────────────┬──────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────┐
│              Agent 收到的消息                     │
│                                                   │
│  [TaskSense System — 当前正在执行: 自动分类]      │
│                                                   │
│  允许的操作 ✓                                     │
│  - 6 个读工具始终可用                              │
│  - 4 个写工具仅限当前任务目标                       │
│                                                   │
│  禁止的操作 ✗                                     │
│  - 启动新任务 / 闲聊 / 假装完成                    │
│                                                   │
│  用户消息: {原始文本}                              │
└─────────────────────────────────────────────────┘
```

---

## 三层防护

### Layer 1：全局行为规则 (`system.md`)

所有 Agent session 的基础行为约束：

```markdown
## Active Task Discipline
- Read-only tools are always permitted when serving the active task
- Write tools must match the task's purpose
- If the user asks something unrelated, politely decline
- Only when get_active_task returns "No active task" are you free
```

### Layer 2：跨 Session 注入 (`task_guard.md`)

当活跃任务存在且当前 session 不是任务自己的 session 时，`orchestrator.ask()` 自动在消息前注入守卫协议：

- `inject_context(question, session_id)` → session 不匹配 → 前缀注入
- `inject_context(question, session_id)` → session 匹配 → 原样返回（工具提示词已有 Task Focus）

### Layer 3：工具提示词 Task Focus

每个工具的提示词开头都有锁定条款：

```markdown
## Task Focus
你正在执行「自动分类」任务，必须完成此任务后才可处理其他请求。
每轮输出前调用 get_active_task 确认任务状态。
如果用户消息与当前任务无关，回复："我正在执行自动分类任务，完成后立即为您处理。"
```

---

## Agent 工具权限矩阵

| 工具 | 分类 | 活跃任务期间 | 说明 |
|------|------|:---:|------|
| `get_active_task` | 状态 | ✅ | 查询当前活跃任务 |
| `search_knowledge_base` | 读 | ✅ | 知识库检索 |
| `lookup_ata_chapter` | 读 | ✅ | ATA 章节查询 |
| `get_board_summary` | 读 | ✅ | 看板统计 |
| `get_task_detail` | 读 | ✅ | 任务详情 |
| `search_related_tasks` | 读 | ✅ | 关联任务搜索 |
| `search_employees` | 读 | ✅ | 员工搜索 |
| `create_task` | 写 | ⚠️ | 仅限当前任务目标 |
| `update_task` | 写 | ⚠️ | 仅限当前任务目标 |
| `classify_task` | 写 | ⚠️ | 仅限当前任务目标 |
| `schedule_task` | 写 | ⚠️ | 仅限当前任务目标 |
| 闲聊 / 无关话题 | — | ❌ | 必须礼貌拒绝 |

---

## 任务生命周期

```
用户触发 _cmd_*
  │
  ├─ set_active(session_id, label, phase, description)
  │   注册为当前活跃任务
  │
  ├─ show_task_card() → 显示进度卡片（蓝→黄→绿→灰）
  │
  ├─ AgentService.ask() → Agent 推理
  │    │
  │    ├─ 交互式工具 (outline, gen_tasks)
  │    │   Phase 1: gathering_requirements → Agent 提问 → 等待用户回复
  │    │   Phase 2: executing → Agent 生成内容
  │    │   → mark_task_done() → 用户点「完成」→ hide_task_card() → clear()
  │    │
  │    └─ 单阶段工具 (classify, schedule, acceptance)
  │        Phase: executing → Agent 处理
  │        → _poll_ghost_resolution() 或直接完成
  │        → _finish_task_card() → clear()
  │
  └─ 弹窗工具 (report, review)
       Phase: executing → Agent 生成内容
       → 线程结束 → clear()
```

---

## 关键组件

### ActiveTaskRegistry (`app/agent/active_task.py`)

```python
class ActiveTaskRegistry:
    def set_active(session_id, label, phase, description)  # 注册任务
    def get_active() -> Optional[ActiveTask]                 # 查询任务
    def clear()                                              # 清除任务
    def update_phase(phase)                                  # 更新阶段
    def is_active() -> bool                                  # 是否有活跃任务
    def inject_context(question, session_id) -> str          # 消息注入
```

线程安全（`threading.Lock`），全局单例 `active_task_registry`。

### get_active_task 工具 (`app/agent/tools/task_state_tools.py`)

Agent 可主动调用以确认当前任务状态：

```
Current Active Task: 自动分类
Phase: executing (started 2026-07-03 15:30:00)
Description: Classifying 5 backlog tasks
---
No active task.   (空闲时)
```

### 任务阶段

| 阶段 | 含义 | 适用工具 |
|------|------|---------|
| `gathering_requirements` | Agent 正在向用户提问 | outline, gen_tasks |
| `executing` | Agent 正在执行任务逻辑 | 全部 |
| `completed` | 任务已完成 | 全部 |

---

## 覆盖的 7 个 AI 工具

| # | 工具 | 提示词 | Session ID | 模式 | 清理路径 |
|---|------|--------|-----------|------|---------|
| 1 | 生成大纲 | `generate_outline_interactive.md` | `outline` | 交互式 | hide_task_card |
| 2 | 生成任务 | `generate_tasks_interactive.md` | `gen_tasks` | 交互式 | _finish_task_card / hide_task_card |
| 3 | 自动分类 | `auto_classify.md` | `classify` | 单阶段+幽灵 | _finish_task_card |
| 4 | 自动排程 | `auto_schedule.md` | `schedule` | 单阶段+幽灵 | _finish_task_card |
| 5 | 自动验收 | `auto_acceptance.md` | `acceptance` | 单阶段 | hide_task_card |
| 6 | 生成报表 | `generate_reports.md` | `report` | 弹窗+线程 | 线程 clear() |
| 7 | 任务审核 | `task_review.md` | `review` | 弹窗+线程 | 线程 clear() |

**额外覆盖**：`review_submission.md`（侧边栏 AI 建议），session_id 为 `review_{task_id}`。

---

## 相关文件

| 文件 | 作用 |
|------|------|
| `app/agent/active_task.py` | 任务注册表核心 |
| `app/agent/prompts/task_guard.md` | 守卫协议模板 |
| `app/agent/tools/task_state_tools.py` | get_active_task 工具 |
| `app/agent/orchestrator.py` | 注入点 + 工具注册 |
| `app/agent/prompts/system.md` | 全局行为规则 |
| `app/agent/prompts/tool_use.md` | 工具文档 + 决策规则 |
| `app/agent/prompts/*.md` | 8 个工具提示词（含 Task Focus） |
| `app/ui/pages/board_page.py` | 7 个 _cmd_* 方法的 set/clear |
| `app/ui/components/ai_chat.py` | hide_task_card 中 clear |

---

## 设计原则

1. **无活跃任务时零影响** — `inject_context` 原样返回消息，所有行为不变
2. **读工具始终可用** — Agent 查询知识库/看板/员工不设限，只要服务于当前任务
3. **写工具受限** — 只能操作当前任务目标，不能越权
4. **防御深度** — 三层提示词叠加（system → task_guard → tool focus），任意一层失效仍有保护
5. **线程安全** — Registry 使用 `threading.Lock`，支持多线程并发访问
