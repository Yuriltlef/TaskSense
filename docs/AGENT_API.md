# Agent API 文档

> 最后更新：2026-07-03  
> 覆盖：Agent 编排器、10 个工具、7 个 AI 命令、内联补全、提交审核

---

## 架构总览

```
┌─────────────────────────────────────────────────────────┐
│ UI 层                                                    │
│  board_page._run_agent_command(cmd)                      │
│  side_panel._ai_suggest → AgentService.review_submission │
│  GhostTextField → AICompletionService                    │
└────────────┬────────────────────────────────────────────┘
             │
┌────────────▼────────────────────────────────────────────┐
│ AgentService (app/ui/services/agent_service.py)          │
│  · 7 个命令入口 + 离线降级                               │
│  · review_submission() 提交审核                          │
│  · _build_submission_context() 共享上下文构建             │
└────────────┬────────────────────────────────────────────┘
             │
┌────────────▼────────────────────────────────────────────┐
│ AgentOrchestrator (app/agent/orchestrator.py)            │
│  · ask() → _agent_loop() → LLM ↔ Tools (max 3 rounds)   │
│  · _parse_tool_calls(): ```tool\nname\nk=v``` 格式       │
│  · ToolExecutor.execute(): 10 个工具路由                 │
└────────────┬──────────────────────────┬─────────────────┘
             │                          │
┌────────────▼──────────┐  ┌────────────▼─────────────────┐
│ LLMClient             │  │ Tools (LangChain @tool)      │
│ · chat_messages()     │  │ · board_tools (4)            │
│ · OpenAI-compatible   │  │ · search_tools (2)           │
│ · timeout=30s         │  │ · write_tools (4)            │
└───────────────────────┘  └──────────────────────────────┘
```

---

## 一、LLMClient

**文件**：`app/agent/llm_client.py`  
**单例**：`from app.agent.llm_client import llm`

### 配置（settings.json → LLM 节）

```json
{
  "llm": {
    "api_key": "sk-...",
    "base_url": "https://api.anthropic.com",
    "model": "claude-sonnet-4-6",
    "temperature": 0.0,
    "max_tokens": 4096
  }
}
```

### API

| 方法 | 签名 | 说明 |
|------|------|------|
| `is_available` | `→ bool` | api_key 非空即 True |
| `chat(system, user)` | `→ str` | 单轮（遗留接口） |
| `chat_messages(msgs)` | `→ str` | 多轮 `[{role, content}]` |
| `model` | `→ str` | 实时读取配置 |
| `temperature` | `→ float` | 实时读取配置 |
| `max_tokens` | `→ int` | 实时读取配置 |

**特性**：配置变更无需重启——每次 `chat()` 都实时读取 `SettingsManager`。内部缓存 OpenAI client，仅在 key/url 变更时重建。

---

## 二、10 个 Agent 工具

### 检索类（2 个）

#### `search_knowledge_base`
```
参数: query (必填), top_k (默认5), doc_type (可选)
返回: 格式化搜索结果文本（含来源、ATA、相关度）
```
混合检索（语义 + 关键词），可过滤 doc_type：`amm|fim|ad|ac|amt_handbook|sb|regulation|textbook`

#### `lookup_ata_chapter`
```
参数: ata_code (必填)，如 "32" 或 "32-41-03"
返回: 该 ATA 章节的知识库内容
```

### 看板类（4 个）

#### `get_board_summary`
```
参数: 无
返回: 各列任务数 + 优先级分布 + 逾期 + 机队摘要
```

#### `get_task_detail`
```
参数: task_id (必填)
返回: 完整字段（标题/状态/优先级/ATA/飞机/负责人/工时/截止/RII/AD）
```

#### `search_related_tasks`
```
参数: ata_chapter (必填)
返回: 同 ATA 章节的所有任务（最多10条）
```

#### `search_employees`
```
参数: query (可选，空=全部)
返回: 匹配的员工列表（ID/姓名/工种/认证/可用性，最多20条）
```

### 写入类（4 个）

#### `create_task`
```
参数: tasks_json (必填) — JSON 数组字符串
  [{title (必填), description, aircraft_reg, ata_chapter,
    priority (默认cat_c), task_type (默认troubleshoot),
    zone, estimated_hours, employee_id, employee_name}]
返回: JSON [{id, work_order_id, title, status:"proposed"}]
```
特性：创建后自动标记 `ai_proposed=True`，以幽灵卡片显示，等待用户确认。

#### `update_task`
```
参数: task_id (必填), fields_json (必填) — JSON 对象
返回: JSON {task_id, work_order_id, title, updated_fields}
```

#### `classify_task`
```
参数: task_id (必填), priority (必填: aog|cat_a|cat_b|cat_c|cat_d)
返回: JSON {task_id, title, priority, status:"triage"}
```
约束：仅 backlog 状态可分类。

#### `schedule_task`
```
参数: task_id (必填), planned_start, planned_end (YYYY-MM-DD HH:MM),
      employee_id, employee_name, estimated_hours
返回: JSON {task_id, title, status:"scheduled", updates}
```
约束：仅 triage 状态可排程。

---

## 三、AgentService API

**文件**：`app/ui/services/agent_service.py`  
**导入**：`from app.ui.services.agent_service import AgentService`

### 核心方法

| 方法 | 签名 | 说明 |
|------|------|------|
| `ask` | `(question, session_id, strict?, cancel_event?) → str` | 通用 Agent 提问，保持多轮上下文 |
| `clear_session` | `(session_id)` | 清除会话历史 |
| `get_board_summary` | `() → str` | 直接调用工具（不经过 LLM） |
| `search_knowledge` | `(query) → str` | 直接调用知识库检索 |
| `get_suggestions` | `(description) → dict` | 任务模板建议（离线可用） |
| `check_compliance` | `(task_id) → dict` | 合规检查（离线可用） |
| `get_daily_report` | `() → str` | 每日报表（离线可用） |

### 7 个 AI 命令

| 方法 | 调用方式 | 离线降级 |
|------|---------|---------|
| `generate_outline(desc)` | `_try_agent("generate_outline.md")` | 关键词推断 ATA + 模板大纲 |
| `generate_tasks(outline?)` | `_try_agent("generate_tasks.md")` | 提示配置 API Key |
| `auto_classify(task_ids?)` | `_try_agent("auto_classify.md")` | 列出待处理任务 + 提示 |
| `auto_schedule(task_ids?)` | `_try_agent("auto_schedule.md")` | 列出已分类任务 + 提示 |
| `auto_acceptance(task_ids?)` | `_try_agent("auto_acceptance.md")` | 列出验收任务 + 提示 |
| `generate_report(type)` | `_try_agent("generate_reports.md")` | board_service 统计报表 |
| `task_review(task_ids?)` | `_try_agent("task_review.md")` | 基本合规检查（6 维度） |

### 提交审核（新增）

#### `review_submission(task_id) → str`
```python
# 单任务提交审核，供侧边栏「AI 建议」按钮调用
# 内部流程：
#   1. _build_submission_context(task) — 构建上下文
#   2. _try_agent("review_submission.md") — 调用 LLM
#   3. 离线降级 → _offline_review(task) — 基本合规检查
```

#### `_build_submission_context(task) → str`
```python
# 构建任务提交审核上下文，输出格式：
#   任务ID / 工卡号 / 标题 / 描述 / 飞机 / ATA / 区域 / 优先级 / 类型
#   负责人 / 预估&实际工时 / 计划时间 / RII / 检查员 / 阻塞状态
#   === 提交材料（交接班日志）===
#   <日志内容 或 "（无提交日志）">
#   === 检查清单 ===
#   [✓/✗] 逐项
#   AD / SB 引用

# 此方法被 review_submission 和 auto_acceptance 共用
```

### 离线降级机制

```python
AgentService._try_agent(prompt_file, user_msg, session_id, fallback)
    → llm.is_available? 
        → Yes: agent.ask(prompt + user_msg)
        → No:  return fallback
```

每个命令的 fallback 基于以下数据源（无需 LLM）：
- **看板统计**：`board_service.get_stats()` / `get_fleet_summary()`
- **任务列表**：`state.get_all_tasks()` 过滤 + 格式化
- **知识库**：`_guess_ata()` 关键词匹配（70+ 关键词 → ATA 章节）
- **员工**：`employee_service.get_employee()`
- **模板**：预定义 Markdown 模板

---

## 四、内联自动补全

### GhostTextField

**文件**：`app/ui/widgets/ghost_text.py`

```
┌─ TextField ─┬─ 幽灵文本(灰色斜体) ─┬─ Ctrl+Space ─┐
├─ AISuggestionBar (chip 建议条) ────────────────────┤
│  [ATA 32-41-03] [描述: 排故…] [区域: 710]        │
└────────────────────────────────────────────────────┘
```

**快捷键**：`Ctrl+Space` 接受内联幽灵文本，`Esc` 清除。

**智能过滤**：约束字段（ATA/注册号/员工/任务类型）只显示自己类型的 chip；自由字段（标题/描述）显示全部。

**幽灵文本优先级**：`title(0) > ata_chapter(1) > description(2) > task_type(3) > zone(4) > employee_name(5)`

### AICompletionService

**文件**：`app/ui/services/ai_completion.py`

**两层体系**：
1. **关键词层**（< 1ms）：70+ 关键词 → ATA 映射，业务规则推理，员工查表
2. **LLM Agent 层**（600ms 防抖）：调用 LLM 进行跨字段推理

**跨字段推理规则**：
- 标题 → ATA + 描述 + 任务类型 + 区域
- ATA → 标题 + 描述 + 区域
- 员工 ID → 姓名（EmployeeService 查表）
- 全上下文 → 缺失字段补全

**缓存机制**：
- 缓存 key = `"字段|文本|k1=v1|k2=v2..."`（上下文序列化）
- 同输入+同上下文 → 0ms 秒出，不触发 Agent 防抖
- Agent 结果同步更新缓存

---

## 五、任务提交审核

### 流程图

```
in_progress → "提交验收" → 填写交接班日志 + 实际工时
  → state.update_task(shift_handover_log, actual_hours)  ← 持久化
  → state.move_task("inspection")                         ← 进入验收
  → log_service.log(SUBMISSION)                           ← 记录日志

inspection → 侧边栏 "AI 建议" → AgentService.review_submission(task_id)
  → _build_submission_context(task)  ← 读取所有字段 + 日志
  → LLM Agent                       ← review_submission.md prompt
  → JSON 解析 → 美化卡片渲染

inspection → "同意" → completed  + log(REVIEW_APPROVE)
inspection → "驳回" → in_progress + log(REVIEW_REJECT)
```

### AI 返回格式

```json
{
  "recommendation": "approve|reject|need_more_info",
  "confidence": 0.95,
  "summary": "一句话摘要",
  "reasons": ["原因1", "原因2"],
  "missing_items": ["缺失项1"],
  "compliance_notes": "AD/SB 合规说明",
  "suggested_actions": ["建议1", "建议2"],
  "risk_level": "low|medium|high"
}
```

### UI 渲染

侧边栏自动解析 JSON 渲染为卡片：
- **结论行**：彩色图标 + 置信度（✅绿色/🔴红色/⚠黄色）
- **摘要**：一句话说明
- **驳回原因/审核要点**：列表
- **缺失项**：警告图标列表
- **合规说明**：灰色文字
- **建议操作**：编号列表
- **风险等级**：彩色标签

解析失败时回退为纯文本渲染。

---

## 六、Agent 编排器

**文件**：`app/agent/orchestrator.py`  
**单例**：`from app.agent.orchestrator import agent`

### `agent.ask(question, session_id, strict?, cancel_event?) → str`

```
用户提问 → conv.add_user(msg)
  → _agent_loop():
    1. LLM 调用
    2. _parse_tool_calls() 检测 ```tool\nname\nk=v``` 块
    3. ToolExecutor.execute() 执行工具
    4. 工具结果反馈给 LLM
    5. 重复 2-4（最多 MAX_TOOL_ROUNDS=3 轮）
    6. 无工具调用 → 返回最终回答
  → conv.add_assistant(response)
```

**工具调用格式**（LLM 输出中嵌入）：
````
```tool
create_task
tasks_json=[{"title": "检查前起落架", "ata_chapter": "32-41-03"}]
```
````

**中断支持**：`cancel_event` 可在每轮循环前检查，实现用户中断回答。

---

## 七、提示词文件

`app/agent/prompts/` 目录：

| 文件 | 用途 | 调用者 |
|------|------|--------|
| `system.md` | 系统角色定义 | 每次 ask() |
| `tool_use.md` | 工具使用说明 + 10 工具参数 | 每次 ask() |
| `normal_mode.md` / `strict_mode.md` | 回答风格 | 每次 ask() |
| `generate_outline.md` | 生成任务大纲 | AgentService.generate_outline |
| `generate_tasks.md` | 批量创建任务 | AgentService.generate_tasks |
| `auto_classify.md` | 自动分类 | AgentService.auto_classify |
| `auto_schedule.md` | 自动排程 | AgentService.auto_schedule |
| `auto_acceptance.md` | 批量验收审核 | AgentService.auto_acceptance |
| `generate_reports.md` | 生成报表 | AgentService.generate_report |
| `task_review.md` | 任务合规审核 | AgentService.task_review |
| `review_submission.md` | 单任务提交审核 | AgentService.review_submission |

---

## 八、UI 入口

| 入口 | 触发 | 目标 |
|------|------|------|
| 标题栏 AI 菜单 | 下拉选择 7 个工具 | `_run_agent_command(cmd)` |
| 搜索框 `>` | 输入 `> 问题` | `_do_agent_query(q)` |
| 搜索框 `/` | `/report` `/compliance` `/kb` | `_do_command(cmd, arg)` |
| `Ctrl+K` | 命令面板 | `_on_command_execute(action)` |
| 任务右键 → "AI 解释" | 上下文菜单 | `_do_agent_query(q)` |
| 侧边栏 "AI 建议" | inspection 任务详情 | `AgentService.review_submission()` |
| 创建任务弹窗 | 输入标题/ATA/描述 | `AICompletionService` → GhostTextField |

---

## 九、离线降级总览

所有 Agent 功能在 LLM 不可用时均能降级运行：

| 功能 | 降级方式 | 降级质量 |
|------|---------|---------|
| 生成大纲 | 关键词推断 ATA + 模板 | ⭐⭐⭐ |
| 生成任务 | 提示配置 API Key | ⭐ |
| 自动分类 | 列出任务 + 提示 | ⭐⭐ |
| 自动排程 | 列出任务 + 提示 | ⭐⭐ |
| 自动验收 | 列出任务 + 提示 | ⭐⭐ |
| 生成报表 | board_service 统计 | ⭐⭐⭐⭐ |
| 任务审核 | 6 维度合规检查 | ⭐⭐⭐⭐ |
| 提交审核 | 6 维度合规检查 | ⭐⭐⭐ |
| 内联补全 | 70+ 关键词 + 业务规则 | ⭐⭐⭐ |
