# TaskSense 未来改进与重构建议

> 基于 2026-07-05 重构完成后的全面审阅

## 当前状态

```
代码: 17,230 行 Python | 119 文件 | 17 模块
测试: 311 passed | 0 failed
bare except: 96 处 | print 残留: 7 处 | TODO: 0
架构评级: A-
```

---

## 一、技术债清理（低风险，高收益）

### 1.1 96 处 bare `except Exception` 替换

**现状**：几乎所有 Flet `.update()` 调用都包裹在裸 `except Exception: pass` 中。

**原因**：Flet 0.28.3 中控件未挂载时调用 `.update()` 会抛 AssertionError，这是防御性编程。

**建议**：统一替换为 `except (AssertionError, Exception): log.debug(...)`，至少记录错误。

**优先级**：中 | **估计**：2-3 小时

### 1.2 7 处 print 残留清理

**位置**：主要在 `employee_service.py`、`log_service.py`、`persistence_service.py`、`loader.py` 中的错误处理路径。

**建议**：全部替换为 `log.warn/error`。

**优先级**：低 | **估计**：30 分钟

### 1.3 `ai_ghost_card.py` 中 `_do_accept` 方法过长

**现状**：~90 行单方法处理 4 种提案类型的 accept 逻辑。

**建议**：拆分为 `_handle_classify`/`_handle_schedule`/`_handle_acceptance`/`_handle_new_task`。

**优先级**：低 | **估计**：1 小时

---

## 二、架构增强（中风险，中收益）

### 2.1 全局单例 → 依赖注入

**现状**：7 个模块级全局单例（`state`/`board_service`/`task_service`/`agent`/`log_service`/`employee_service`/`event_bus`）。

**问题**：无法 mock 用于单元测试，隐式依赖使代码难以理解。

**建议**：
```python
class App:
    def __init__(self):
        self.state = AppState()
        self.task_service = TaskService(self.state)
        self.board_service = BoardService(self.state)
        ...
```

**优先级**：中 | **估计**：2-3 天 | **风险**：需修改所有文件的 import

### 2.2 Task 模型拆分

**现状**：`Task` dataclass 含 40+ 字段（航空数据/人员/合规/零件/AI 元数据）。

**建议**：拆分为子对象：
```python
@dataclass
class AircraftInfo:
    registration: str
    model: str

@dataclass
class ScheduleInfo:
    planned_start: datetime | None
    planned_end: datetime | None
    estimated_hours: float
    employee_id: str
    employee_name: str

@dataclass
class ComplianceInfo:
    is_rii: bool
    inspector: str | None
    ad_numbers: list[str]
    sb_numbers: list[str]
    mel_item: str

@dataclass
class AiMetadata:
    ai_proposed: bool
    ai_priority: Priority | None
    ai_suggestions: list[dict]
    ai_acceptance_recommendation: str | None
    ai_acceptance_reason: str | None

@dataclass
class Task:
    id: str
    title: str
    aircraft: AircraftInfo
    schedule: ScheduleInfo
    compliance: ComplianceInfo
    ai: AiMetadata
    ...
```

**优先级**：中 | **估计**：1-2 天 | **风险**：大量字段访问需改为 `task.aircraft.registration`

### 2.3 序列化框架替换

**现状**：`Task.from_dict()` 和 `Task.to_dict()` 各 ~180 行手动映射，添加新字段需同步改两处。

**建议**：使用 `dataclasses.asdict()` 或 `pydantic` 自动序列化。

**优先级**：中 | **估计**：1 天

---

## 三、功能增强（高收益）

### 3.1 AI 工具注册机制

**现状**：添加新 AI 工具需修改 4 个文件（agent_service + ai_commands + board_page + prompt）。

**建议**：创建 AI 工具注册表：
```python
@dataclass
class AITool:
    name: str           # "自动分类"
    session_id: str     # "classify"
    prompt_file: str    # "auto_classify.md"
    source_column: str  # "backlog"
    target_column: str  # "triage"
    tool_name: str      # "classify_task"

AI_TOOLS = [AITool(...), ...]

# dispatch 自动从注册表生成
def dispatch(cmd):
    tool = AI_TOOLS_REGISTRY[cmd]
    ...
```

**优先级**：中 | **估计**：1 天

### 3.2 测试补充

**现状**：311 测试全是核心业务层，UI 层和 Agent 工具层无测试。

**建议**：
1. ProposalHandler 测试（accept/reject 各类型）
2. CancelCoordinator 测试（单任务/批量）
3. TaskRegistry 线程安全测试
4. BoardRenderer 幽灵卡类型判断测试
5. AI 工具集成测试（mock LLM）

**优先级**：中 | **估计**：2-3 天

### 3.3 撤销/重做系统

**现状**：无任何撤销机制，误操作不可恢复。

**建议**：基于 `state._notify` 事件和 `StatusChange` 历史实现简单的撤销栈。

**优先级**：低 | **估计**：2-3 天

### 3.4 数据导入/导出

**现状**：数据仅保存在 `data/board_state.json`，无导出功能。

**建议**：
- 导出看板为 CSV/Excel 报表
- 导入批量任务
- 看板快照备份

**优先级**：低 | **估计**：1-2 天

---

## 四、性能优化

### 4.1 `BoardState.task_column` 反向索引

**现状**：O(n×m) 遍历所有列 × 所有任务查找任务所在列。

**建议**：维护 `task_id → col_id` 反向映射字典。

**优先级**：低 | **估计**：1 小时

### 4.2 `BoardService.search_tasks` 索引

**现状**：线性 O(n) 扫描全部任务进行文本搜索。

**建议**：对大数据集（>1000 任务）添加缓存索引。

**优先级**：低 | **估计**：2 小时

### 4.3 ChromaDB 向量化批处理优化

**现状**：`store.py` 的 `add_chunks` 使用 batch_size=500。

**建议**：根据 GPU 显存动态调整 batch_size。

**优先级**：低 | **估计**：1 小时

---

## 五、用户体验

### 5.1 任务卡片拖放动画

**现状**：拖放时无平滑动画，卡片瞬移到目标列。

**建议**：使用 Flet 的 `animate_opacity` + `animate_offset` 实现过渡。

**优先级**：低 | **估计**：4-6 小时

### 5.2 键盘快捷键扩展

**现状**：仅支持 Ctrl+K（命令面板）和 Esc（关闭面板）。

**建议**：
- Ctrl+N：新建任务
- Ctrl+F：聚焦搜索框
- Ctrl+Z：撤销（需先实现撤销系统）
- Space：快速预览任务

**优先级**：低 | **估计**：2 小时

### 5.3 暗色/亮色主题切换

**现状**：仅支持暗色主题，theme_mode 字段存在但未实现亮色。

**建议**：实现亮色主题配色方案 + 设置面板切换。

**优先级**：低 | **估计**：1 天

---

## 六、安全与合规

### 6.1 API Key 管理

**现状**：`settings.json` 明文存储 API Key（已提交 git）。

**建议**：
- 从环境变量 `TASKSENSE_API_KEY` 加载
- 创建 `settings.example.json` 模板
- 轮换已泄露的 Key

**优先级**：**高** | **估计**：1 小时

### 6.2 操作审计完善

**现状**：`log_service` 记录部分操作，但缺少：
- 幽灵卡接受/拒绝
- AI 工具调用
- 设置变更

**建议**：扩展 LogType 枚举，在上述事件发生时写入审计日志。

**优先级**：中 | **估计**：2-3 小时

---

## 七、部署与运维

### 7.1 打包为独立安装程序

**现状**：需 Python 环境 + 手动安装依赖。

**建议**：使用 PyInstaller 打包为 Windows .exe。

**优先级**：低 | **估计**：1 天

### 7.2 自动更新机制

**建议**：GitHub Release + 版本检查 + 增量更新。

**优先级**：低 | **估计**：2-3 天

---

## 优先级建议

### 立即做（本周）
1. 🔴 API Key 环境变量化（6.1）
2. 🟡 bare except 替换（1.1）

### 近期做（2 周内）
3. 🟡 AI 工具注册机制（3.1）
4. 🟡 操作审计完善（6.2）
5. 🟡 ProposalHandler/BoardRenderer 测试（3.2）

### 远期做（1-3 月）
6. 🟢 依赖注入（2.1）
7. 🟢 Task 模型拆分（2.2）
8. 🟢 撤销/重做（3.3）
9. 🟢 暗色/亮色主题（5.3）
