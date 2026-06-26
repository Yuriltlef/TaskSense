# TaskSense 后端架构（核心层 + Agent 层 + 知识库层）

## 架构概览

```
┌──────────────────────────────────────────────────────────┐
│                      UI 层 (app/ui/)                      │
│                   通过 Controller 调用                     │
└──────────────────────────┬───────────────────────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
┌─────────────────┐ ┌─────────────┐ ┌─────────────────┐
│   core/services/  │ │  agent/      │ │  knowledge/      │
│   业务服务层       │ │  Agent 层    │ │  RAG 知识库层    │
└────────┬────────┘ └──────┬──────┘ └────────┬────────┘
         │                 │                 │
         ▼                 ▼                 ▼
┌─────────────────┐ ┌─────────────┐ ┌─────────────────┐
│   core/models/   │ │ agent/tools/ │ │  data/          │
│   数据模型        │ │ Agent 工具    │ │  持久化存储      │
└─────────────────┘ └─────────────┘ └─────────────────┘
```

---

## 第一部分：核心层 (`app/core/`)

### 1.1 数据模型 (`models/`)

#### Task 模型

```python
# app/core/models/task.py

from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from typing import Optional

class Priority(Enum):
    AOG = "aog"         # 飞机停飞 — 立即
    CAT_A = "cat_a"     # 当日修复
    CAT_B = "cat_b"     # 72小时
    CAT_C = "cat_c"     # 240小时
    CAT_D = "cat_d"     # 2880小时（长期延期）

class TaskType(Enum):
    TROUBLESHOOT = "troubleshoot"  # 排故
    INSPECTION = "inspection"      # 检查
    SERVICING = "servicing"        # 勤务
    REMOVAL_INSTALL = "r_i"       # 拆卸/安装
    TEST = "test"                  # 测试
    REPAIR = "repair"              # 修复

class TaskStatus(Enum):
    BACKLOG = "backlog"
    TRIAGE = "triage"
    SCHEDULED = "scheduled"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    INSPECTION = "inspection"
    PARTS_HOLD = "parts_hold"
    COMPLETED = "completed"
    ARCHIVED = "archived"

@dataclass
class Task:
    id: str
    title: str
    description: str = ""
    
    # 航空领域核心字段
    aircraft_reg: str = ""               # 飞机注册号 (尾号)
    aircraft_model: str = ""             # 机型 (如 737-800)
    ata_chapter: str = ""                # ATA 章节 (如 "32-41-03")
    ata_page_block: str = ""             # 页面块类型 (如 "101" = 排故)
    zone: str = ""                       # 区域 (如 "710")
    
    # 分类
    priority: Priority = Priority.CAT_C
    task_type: TaskType = TaskType.TROUBLESHOOT
    status: TaskStatus = TaskStatus.BACKLOG
    
    # 时间
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    due_date: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # 资源
    assignee: Optional[str] = None       # 指派技师
    estimated_hours: float = 0.0
    actual_hours: float = 0.0
    
    # 关联
    parent_task_id: Optional[str] = None  # 父任务
    blocked_by: list[str] = field(default_factory=list)  # 阻塞依赖
    related_wo_ids: list[str] = field(default_factory=list)  # 关联工单
    
    # 合规
    ad_numbers: list[str] = field(default_factory=list)  # 适用AD
    sb_numbers: list[str] = field(default_factory=list)  # 适用SB
    is_rii: bool = False                 # 必检项目
    
    # AI 标记
    ai_priority: Optional[Priority] = None  # AI 建议优先级
    ai_suggestions: list[dict] = field(default_factory=list)
    rag_references: list[dict] = field(default_factory=list)
    
    # 清单
    checklist: list["ChecklistItem"] = field(default_factory=list)
    
    # 状态追踪
    status_history: list["StatusChange"] = field(default_factory=list)

@dataclass
class ChecklistItem:
    id: str
    text: str
    completed: bool = False
    completed_by: Optional[str] = None
    completed_at: Optional[datetime] = None

@dataclass
class StatusChange:
    from_status: TaskStatus
    to_status: TaskStatus
    timestamp: datetime
    changed_by: str
    comment: str = ""
```

#### Aircraft 模型

```python
# app/core/models/aircraft.py

@dataclass
class Aircraft:
    registration: str         # 注册号（主键）
    model: str                # 机型
    msn: str                  # 制造商序列号
    status: AircraftStatus    # 运行中 / 维修中 / AOG / 封存
    total_hours: float        # 总飞行小时 (TAH)
    total_cycles: int         # 总循环数 (TAC)
    last_a_check: datetime
    last_c_check: datetime
    last_d_check: datetime
    current_location: str     # 当前位置（机库/停机位）
    mel_items: list[str]      # 当前 MEL 延期项
    due_tasks_count: int      # 待处理任务数
    
class AircraftStatus(Enum):
    OPERATIONAL = "operational"
    IN_MAINTENANCE = "in_maintenance"
    AOG = "aog"
    STORED = "stored"
```

#### Kanban/Board 模型

```python
# app/core/models/kanban.py

@dataclass
class ColumnConfig:
    id: str
    title: str
    status: TaskStatus
    wip_limit: Optional[int] = None
    order: int = 0
    visible: bool = True

@dataclass
class BoardState:
    columns: list[ColumnConfig]
    tasks: dict[str, list[str]]     # col_id -> [task_id, ...]
    swimlane_by: Optional[str] = None  # "ata" | "aircraft" | "team" | None

@dataclass
class FilterState:
    search_query: str = ""
    ata_chapters: list[str] = field(default_factory=list)
    aircraft_regs: list[str] = field(default_factory=list)
    priorities: list[Priority] = field(default_factory=list)
    task_types: list[TaskType] = field(default_factory=list)
    assignees: list[str] = field(default_factory=list)
    due_date_range: tuple[Optional[datetime], Optional[datetime]] = (None, None)
    show_completed: bool = False
```

---

### 1.2 状态管理器 (`state.py`)

```python
# app/core/state.py

class AppState:
    """
    全局应用状态 — 单一状态树。
    
    不依赖任何 UI 框架。通过事件回调通知变更。
    """
    
    def __init__(self):
        self._board_state = BoardState(columns=DEFAULT_COLUMNS, tasks={})
        self._tasks: dict[str, Task] = {}
        self._aircraft: dict[str, Aircraft] = {}
        self._filters = FilterState()
        self._listeners: list[callable] = []
    
    # ── 状态读取 ──
    def get_task(self, task_id: str) -> Optional[Task]: ...
    def get_tasks_by_column(self, col_id: str) -> list[Task]: ...
    def get_aircraft(self, reg: str) -> Optional[Aircraft]: ...
    def get_filtered_board(self) -> BoardState: ...
    
    # ── 状态变更 ──
    def add_task(self, task: Task): ...
    def update_task(self, task_id: str, **changes): ...
    def move_task(self, task_id: str, to_col: str, index: int): ...
    def delete_task(self, task_id: str): ...
    def set_filters(self, filters: FilterState): ...
    
    # ── 变更监听 ──
    def subscribe(self, listener: callable):
        """注册状态变更回调。listener() 在每次变更后被调用。"""
    
    def _notify(self):
        for listener in self._listeners:
            listener()
```

**设计要点：**
- 所有状态变更通过 `AppState` 方法进行，不允许直接修改内部字段
- 每次变更后自动 `_notify()`，触发 UI 刷新
- 状态对象不可变（返回 `copy`/`deepcopy`）

---

### 1.3 业务服务 (`services/`)

#### TaskService

```python
# app/core/services/task_service.py

class TaskService:
    """
    任务生命周期管理。
    
    不依赖 UI，不依赖 Agent。
    每个方法执行前做业务校验。
    """
    
    def __init__(self, state: AppState, validators: TaskValidators):
        self.state = state
        self.validators = validators
    
    def create_task(self, data: TaskCreateData) -> Task:
        """创建任务，自动分配到 Triage 或 Backlog 列"""
        # 1. 校验数据
        self.validators.validate_create(data)
        # 2. 创建 Task 实例
        task = Task(id=generate_id(), **data.dict())
        # 3. 写入状态
        self.state.add_task(task)
        return task
    
    def move_task(self, task_id: str, to_column: str, index: int = -1):
        """
        移动任务到目标列。
        
        校验规则：
        - to_column 必须存在
        - 不能跳过必须的列（如不能从 Backlog 直接到 Completed）
        - 如果移到 In Progress，检查 WIP 限制
        - 如果移到 Ready，检查零件是否全部到位
        """
        task = self.state.get_task(task_id)
        self.validators.validate_transition(task, to_column)
        
        # 记录状态变更历史
        task.status_history.append(StatusChange(
            from_status=task.status,
            to_status=column_status(to_column),
            timestamp=datetime.now(),
            changed_by=current_user(),
        ))
        
        self.state.move_task(task_id, to_column, index)
    
    def assign_task(self, task_id: str, assignee: str): ...
    def update_checklist(self, task_id: str, item_id: str, completed: bool): ...
    def add_comment(self, task_id: str, comment: str): ...
    def set_due_date(self, task_id: str, due: datetime): ...
    def delete_task(self, task_id: str):
        """软删除，移到 Archived 列"""
        ...
```

#### BoardService

```python
# app/core/services/board_service.py

class BoardService:
    """
    看板操作服务。
    """
    
    def __init__(self, state: AppState):
        self.state = state
    
    def get_board(self, filters: FilterState) -> BoardState:
        """返回过滤后的看板状态，供 UI 消费"""
        ...
    
    def search_tasks(self, query: str) -> list[Task]:
        """混合搜索：精确匹配（ATA码、尾号、零件号）+ 语义搜索"""
        ...
    
    def reorder_column(self, col_id: str, task_ids: list[str]):
        """列内排序"""
        ...
    
    def set_swimlane(self, by: Optional[str]):
        """设置 Swimlane 分组维度"""
        ...
    
    def get_fleet_status(self) -> FleetStatus:
        """机队概览：各状态飞机数、逾期任务数等"""
        ...
```

#### ReportService

```python
# app/core/services/report_service.py

class ReportService:
    """
    报告生成服务。
    
    负责数据聚合，文本生成委托给 Agent。
    """
    
    def __init__(self, state: AppState, report_agent):
        self.state = state
        self.report_agent = report_agent
    
    def generate_shift_report(self, shift_date: date) -> str:
        """生成班次交接报告"""
        tasks = self.state.get_tasks_for_shift(shift_date)
        return self.report_agent.generate_handover(tasks)
    
    def generate_daily_summary(self) -> dict:
        """每日统计：完成数、进行中、阻塞、平均工时等"""
        ...
    
    def generate_compliance_report(self) -> list[dict]:
        """AD/SB 合规状态报告"""
        ...
```

---

### 1.4 业务校验 (`validators.py`)

```python
# app/core/validators.py

class TaskValidators:
    """
    任务操作前的业务规则校验。
    
    所有校验失败抛出 BusinessRuleViolation，包含可展示的错误信息。
    """
    
    # 允许的状态转换映射
    ALLOWED_TRANSITIONS = {
        TaskStatus.BACKLOG:    [TaskStatus.TRIAGE, TaskStatus.ARCHIVED],
        TaskStatus.TRIAGE:     [TaskStatus.SCHEDULED, TaskStatus.BACKLOG],
        TaskStatus.SCHEDULED:  [TaskStatus.READY, TaskStatus.BACKLOG],
        TaskStatus.READY:      [TaskStatus.IN_PROGRESS, TaskStatus.SCHEDULED],
        TaskStatus.IN_PROGRESS:[TaskStatus.INSPECTION, TaskStatus.PARTS_HOLD, TaskStatus.COMPLETED],
        TaskStatus.INSPECTION: [TaskStatus.COMPLETED, TaskStatus.IN_PROGRESS],
        TaskStatus.PARTS_HOLD: [TaskStatus.READY, TaskStatus.SCHEDULED],
        TaskStatus.COMPLETED:  [TaskStatus.ARCHIVED],
        TaskStatus.ARCHIVED:   [],  # 不可移出
    }
    
    def validate_transition(self, task: Task, to_column: str): ...
    def validate_create(self, data: TaskCreateData): ...
    def validate_wip(self, column_id: str): ...
```

---

### 1.5 事件总线 (`events.py`)

```python
# app/core/events.py

from enum import Enum
from dataclasses import dataclass
from typing import Callable

class EventType(Enum):
    TASK_CREATED = "task_created"
    TASK_MOVED = "task_moved"
    TASK_UPDATED = "task_updated"
    TASK_DELETED = "task_deleted"
    TASK_OVERDUE = "task_overdue"
    WIP_EXCEEDED = "wip_exceeded"
    ANOMALY_DETECTED = "anomaly_detected"
    COMPLIANCE_ALERT = "compliance_alert"
    REPORT_GENERATED = "report_generated"

@dataclass
class AppEvent:
    type: EventType
    data: dict
    timestamp: datetime

class EventBus:
    """
    发布/订阅事件总线。
    
    用于跨层通信（如 Agent 异常检测 → 通知 UI）。
    """
    
    def __init__(self):
        self._handlers: dict[EventType, list[Callable]] = {}
    
    def on(self, event_type: EventType, handler: Callable): ...
    def emit(self, event: AppEvent): ...
```

---

## 第二部分：Agent 层 (`app/agent/`)

### 2.1 Agent 架构

```
agent/orchestrator.py (Agent 编排器)
    │
    ├── triage.py          → Triage Agent
    ├── suggest.py         → Suggest Agent
    ├── compliance.py      → Compliance Agent
    ├── report.py          → Report Agent
    └── anomaly.py         → Anomaly Agent
         │
         └── tools/        → 共享工具函数
              ├── board_tools.py
              ├── search_tools.py
              └── report_tools.py
```

### 2.2 Agent 定义规范

每个 Agent 遵循统一接口：

```python
class BaseAgent:
    """Agent 基类"""
    
    # LangChain Agent 实例
    agent: Any
    
    # 提示词模板
    system_prompt: str
    
    # 可用工具列表
    tools: list[BaseTool]
    
    # 自主权级别
    autonomy_level: AutonomyLevel
    
    async def run(self, input_data: dict) -> AgentResult:
        """
        执行 Agent 推理。
        
        Args:
            input_data: 输入上下文（任务信息、用户意图等）
            
        Returns:
            AgentResult: 结构化输出
        """
        ...

@dataclass
class AgentResult:
    success: bool
    data: dict
    citations: list[Citation]   # RAG 引用来源
    reasoning: str              # Agent 推理过程（透明性）
    requires_approval: bool     # 是否需要人工审批

@dataclass
class Citation:
    source_type: str            # "amm" | "fim" | "ad" | "sb" | "history"
    source_id: str              # 文档标识
    ata_chapter: str
    snippet: str               # 引用片段
    relevance_score: float
```

### 2.3 Triage Agent

```python
# app/agent/triage.py

class TriageAgent(BaseAgent):
    """
    自动分类 Agent — 自主权: 低（全自动）。
    
    职责：
    - 分析新任务，自动分配 ATA 章节
    - 自动判定优先级（AOG/A/B/C/D）
    - 自动匹配任务类型
    
    输入：故障描述、飞机型号、发现时机（WHF码）
    输出：ATA章节、优先级、任务类型、相关故障码
    """
    
    system_prompt = """
    你是航空维修分类专家。根据故障描述和飞机信息，判定：
    1. ATA 章节号（如 32-41-03）
    2. 优先级（AOG/CatA/B/C/D），参考 MEL 标准
    3. 任务类型（排故/检查/勤务/拆装/测试）
    
    规则：
    - 涉及飞行安全/无法放行 → AOG
    - 涉及 MEL 可延期项目 → Cat A/B 根据 MEL 时限
    - 常规故障 → Cat C
    - 非安全相关 → Cat D
    
    输出 JSON 格式，附带 ATA 手册引用。
    """
    
    tools = [
        query_ata_index,       # 查 ATA 章节定义
        search_mel,            # 查 MEL 延期时限
        search_history,        # 查相似历史工单
    ]
    
    autonomy_level = AutonomyLevel.LOW  # 全自动，事后审查
```

### 2.4 Suggest Agent

```python
# app/agent/suggest.py

class SuggestAgent(BaseAgent):
    """
    操作建议 Agent — 自主权: 中（建议+确认）。
    
    职责：
    - 根据 ATA 章节和任务类型检索标准工卡模板
    - 推荐操作步骤
    - 推荐所需工具和零件
    - 推荐关联检查项目
    
    输入：任务上下文（ATA章、飞机型号、故障描述）
    输出：建议的操作步骤、关联工卡模板、工具/零件清单
    """
    
    system_prompt = """
    你是航空维修操作顾问。根据任务上下文，从知识库中检索：
    1. 适用的标准工卡模板
    2. 推荐的操作步骤（仅检索手册内容，不创造新步骤）
    3. 所需的工具和零件
    4. 相关的检查清单
    
    重要：你只能检索和引用已认证的手册内容，绝不生成新的维护程序。
    """
    
    tools = [
        search_amm,            # 检索 AMM 程序
        search_fim,            # 检索 FIM 排故树
        search_parts,          # 查询零件目录
        get_task_template,     # 获取工卡模板
    ]
    
    autonomy_level = AutonomyLevel.MEDIUM  # 建议需人工确认
```

### 2.5 Compliance Agent

```python
# app/agent/compliance.py

class ComplianceAgent(BaseAgent):
    """
    合规检查 Agent — 自主权: 高（草稿+强制审批）。
    
    职责：
    - 检查 AD 适用性
    - 检查 SB 适用性
    - 检查寿命件到期
    - 验证放行前合规条件
    
    输入：任务上下文、飞机信息
    输出：适用的 AD/SB 清单、合规状态、必检项标记
    """
    
    system_prompt = """
    你是航空适航合规审查员。检查以下内容：
    1. 适用的适航指令（AD）— 必须执行
    2. 适用的服务通告（SB）— 建议执行
    3. 寿命件到期检查
    4. 必检项目（RII）识别
    
    输出合规状态：COMPLIANT / NON-COMPLIANT / NEEDS_REVIEW
    """
    
    tools = [
        search_ad_database,    # AD 数据库查询
        search_sb_database,    # SB 数据库查询
        check_llp_status,      # 寿命件状态
        check_rii_requirements,# RII 要求
    ]
    
    autonomy_level = AutonomyLevel.HIGH  # 仅生成草稿，必须审批
```

### 2.6 Report Agent

```python
# app/agent/report.py

class ReportAgent(BaseAgent):
    """
    报告生成 Agent — 自主权: 低（全自动，结果可审查）。
    
    职责：
    - 生成班次交接摘要
    - 生成每日/每周完成统计
    - 生成异常检测报告
    - 生成合规报告
    """
    
    tools = [
        get_board_statistics,  # 看板统计数据
        get_anomaly_events,    # 异常事件列表
        get_compliance_status, # 合规状态
    ]
    
    autonomy_level = AutonomyLevel.LOW
```

### 2.7 Anomaly Agent

```python
# app/agent/anomaly.py

class AnomalyAgent(BaseAgent):
    """
    异常检测 Agent — 自主权: 低（自动告警，事后审查）。
    
    职责：
    - 检测重复故障模式（同飞机同ATA近期重复）
    - 检测异常工时（远超同类任务均值）
    - 检测逾期任务积累
    - 检测零件频繁短缺模式
    
    触发方式：定时扫描 + 事件驱动
    """
    
    tools = [
        query_task_history,
        get_ata_statistics,
        check_part_availability,
    ]
    
    autonomy_level = AutonomyLevel.LOW
```

### 2.8 Agent 编排器

```python
# app/agent/orchestrator.py

class AgentOrchestrator:
    """
    协调多个 Agent 的执行。
    
    典型流程：
    1. 用户创建任务 → Triage Agent（自动分类）+ Suggest Agent（建议）
    2. 任务排程 → Scheduling Agent（排程建议）
    3. 任务执行 → Suggest Agent（步骤建议）+ Compliance Agent（合规检查）
    4. 定时触发 → Anomaly Agent（异常扫描）+ Report Agent（报告生成）
    """
    
    def __init__(self, config, knowledge_base):
        self.triage = TriageAgent(...)
        self.suggest = SuggestAgent(...)
        self.compliance = ComplianceAgent(...)
        self.report = ReportAgent(...)
        self.anomaly = AnomalyAgent(...)
    
    async def on_task_created(self, task: Task) -> dict:
        """新任务创建时：自动分类 + 操作建议"""
        triage_result = await self.triage.run({"task": task})
        suggest_result = await self.suggest.run({"task": task})
        return {
            "triage": triage_result,
            "suggest": suggest_result,
        }
    
    async def on_scheduled(self, task: Task): ...
    
    async def on_daily_scan(self):
        """每日定时：异常检测 + 报告生成"""
        anomaly_results = await self.anomaly.run({})
        report = await self.report.run({"type": "daily"})
        return {"anomalies": anomaly_results, "report": report}
```

---

### 2.9 Agent 工具函数 (`tools/`)

```python
# app/agent/tools/board_tools.py

@tool
def get_board_state() -> dict:
    """获取当前看板状态（供 Agent 查询）"""
    ...

@tool
def get_task_details(task_id: str) -> dict:
    """获取任务完整详情"""
    ...

@tool
def get_fleet_status() -> dict:
    """获取机队状态概览"""
    ...


# app/agent/tools/search_tools.py

@tool
def search_amm(query: str, ata_chapter: Optional[str] = None) -> list[dict]:
    """检索飞机维护手册（AMM）"""
    ...

@tool
def search_fim(fault_code: str) -> dict:
    """检索故障隔离手册（FIM）"""
    ...

@tool
def search_history(query: str, aircraft_reg: Optional[str] = None) -> list[dict]:
    """检索历史工单"""
    ...

@tool
def search_mel(equipment: str) -> dict:
    """检索 MEL 延期时限"""
    ...


# app/agent/tools/report_tools.py

@tool
def get_board_statistics(date_range: tuple) -> dict: ...
@tool
def get_anomaly_events(days: int = 7) -> list[dict]: ...
@tool
def get_compliance_status() -> list[dict]: ...
```

---

## 第三部分：知识库层 (`app/knowledge/`)

### 3.1 知识库架构

```
app/knowledge/
├── loader.py          # 文档加载（PDF、HTML、Markdown）
├── chunker.py         # ATA 层级感知分块
├── embedder.py        # 向量化
├── store.py           # 向量存储抽象
├── retriever.py       # 混合检索
└── ata_index.py       # ATA 章节索引
```

### 3.2 文档加载器

```python
# app/knowledge/loader.py

class DocumentLoader:
    """
    统一文档加载接口。
    
    支持格式：PDF、HTML、Markdown、纯文本
    来源：本地文件、URL、数据库
    """
    
    def load_directory(self, path: str) -> list[Document]:
        """加载目录下所有支持的文档"""
        ...
    
    def load_url(self, url: str) -> Document:
        """从 URL 加载文档"""
        ...
    
    def parse_ata_metadata(self, doc: Document) -> dict:
        """
        从文档中提取 ATA 元数据：
        - 章节号
        - 页面块类型
        - 适用机型
        - 修订版本
        """
        ...
```

### 3.3 层级感知分块器

```python
# app/knowledge/chunker.py

class HierarchicalChunker:
    """
    ATA 层级感知分块策略。
    
    保留文档的树状结构，每个块附加：
    - title_chain: "32章 → 起落架 → 前轮转向 → 排故程序"
    - ata_chapter: "32-41-03"
    - page_block: "101"
    - parent_chunk_id: 父块 ID
    - applicable_models: ["737-800", "A320neo"]
    
    分块策略：
    - 描述类文档：按段落分块，800 tokens/块，120 重叠
    - 程序类文档：按步骤分块，保持步骤完整性
    - 表格数据：按行分块，保留表头
    """
    
    def chunk(self, doc: Document) -> list[Chunk]:
        ...
    
    def _parse_heading_tree(self, doc: Document) -> dict:
        """解析文档标题树"""
        ...
    
    def _chunk_by_page_block_type(self, doc: Document, block_type: str):
        """按页面块类型选择不同分块策略"""
        if block_type in ("001-099",):  # 描述类
            return self._chunk_semantic(doc, max_tokens=800, overlap=120)
        elif block_type in ("101-199",):  # 排故类
            return self._chunk_by_heading(doc)  # 按标题边界
        elif block_type in ("201-299", "401-499", "501-599"):  # 程序类
            return self._chunk_by_procedure_step(doc)
        ...
```

### 3.4 向量化

```python
# app/knowledge/embedder.py

class Embedder:
    """
    文本向量化抽象。
    
    支持切换嵌入模型（通过配置）。
    """
    
    def __init__(self, model_name: str):
        self.model = self._load_model(model_name)
    
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """批量向量化"""
        ...
    
    def embed_query(self, text: str) -> list[float]:
        """单条查询向量化（可加提示词前缀）"""
        # 查询时添加领域前缀提高精度
        text = f"航空维护查询: {text}"
        return self.model.embed(text)
```

### 3.5 向量存储

```python
# app/knowledge/store.py

from abc import ABC, abstractmethod

class VectorStore(ABC):
    """向量存储抽象 — 支持切换 Chroma / Qdrant"""
    
    @abstractmethod
    def add(self, chunks: list[Chunk]): ...
    
    @abstractmethod
    def search(self, query_embedding: list[float], top_k: int = 10,
               filters: Optional[dict] = None) -> list[SearchResult]: ...
    
    @abstractmethod
    def delete(self, filters: dict): ...

class ChromaStore(VectorStore):
    """Chroma 实现"""
    ...

class QdrantStore(VectorStore):
    """Qdrant 实现"""
    ...
```

### 3.6 混合检索器

```python
# app/knowledge/retriever.py

class HybridRetriever:
    """
    混合检索器 = BM25 关键词 + 向量语义 + ATA 章节过滤。
    
    使用 Reciprocal Rank Fusion (RRF) 融合排序。
    
    检索流程：
    1. BM25 精确匹配（零件号、故障码、ATA章节号）
    2. 向量语义搜索（症状描述、模糊查询）
    3. ATA 层级扩展（匹配到的节点 → 包含父级和兄弟节点）
    4. RRF 融合排序
    """
    
    def __init__(self, vector_store: VectorStore, ata_index: 'ATAIndex'):
        self.vector_store = vector_store
        self.bm25 = BM25Retriever()
        self.ata_index = ata_index
    
    def retrieve(self, query: str, top_k: int = 10,
                 filters: Optional[dict] = None) -> list[SearchResult]:
        """
        执行混合检索。
        
        filters 支持：
        - ata_chapter: "32-41-03"
        - aircraft_model: "737-800"
        - page_block_type: "101-199"
        """
        # 1. 关键词匹配
        kw_results = self.bm25.search(query, top_k=top_k)
        
        # 2. 向量搜索
        vec_results = self.vector_store.search(
            self.embedder.embed_query(query), top_k=top_k, filters=filters
        )
        
        # 3. ATA 层级扩展
        expanded = self._expand_by_ata_hierarchy(vec_results)
        
        # 4. RRF 融合
        return self._rrf_fusion(kw_results, expanded)
    
    def _expand_by_ata_hierarchy(self, results: list[SearchResult]) -> list[SearchResult]:
        """将匹配节点的父级和兄弟节点也纳入结果"""
        ...

@dataclass
class SearchResult:
    chunk_id: str
    content: str
    metadata: dict              # ATA 章节、机型、页面块类型等
    score: float
    source: str                 # 文档来源
    title_chain: str            # 层级路径
```

### 3.7 ATA 章节索引

```python
# app/knowledge/ata_index.py

class ATAIndex:
    """
    ATA 100 章节索引 — 航空维护知识库的核心导航结构。
    
    维护 ATA 章节的树状关系和元数据：
    
    32 (起落架)
    ├── 32-10 (主起落架)
    │   ├── 32-11 (主起落架舱门)
    │   ├── 32-12 (主起落架减震支柱)
    │   └── 32-13 (主起落架收放机构)
    ├── 32-20 (前起落架)
    │   ├── 32-21 (前起落架舱门)
    │   ├── 32-22 (前起落架减震支柱)
    │   └── 32-23 (前起落架转向)
    └── 32-40 (刹车与防滑)
        └── 32-41 (刹车系统)
            └── 32-41-03 (刹车组件)
    """
    
    def get_chapter(self, code: str) -> Optional[ATANode]:
        """获取指定章节的完整信息"""
        ...
    
    def get_children(self, code: str) -> list[ATANode]:
        """获取子章节"""
        ...
    
    def get_ancestors(self, code: str) -> list[ATANode]:
        """获取父级链"""
        ...
    
    def get_siblings(self, code: str) -> list[ATANode]:
        """获取同级章节"""
        ...
    
    def search(self, keyword: str) -> list[ATANode]:
        """关键词搜索章节"""
        ...
    
    def get_page_block_types(self, code: str) -> list[str]:
        """获取该章节包含的页面块类型"""
        ...
```

---

## 第四部分：配置层 (`app/config/`)

```python
# app/config/settings.py

@dataclass
class AppSettings:
    """全局配置 — 支持环境变量覆盖"""
    
    # ── 应用 ──
    app_name: str = "TaskSense"
    app_version: str = "0.1.0"
    debug: bool = False
    
    # ── LLM ──
    llm_provider: str = "anthropic"    # anthropic | openai | local
    llm_model: str = "claude-sonnet-4-6"
    llm_temperature: float = 0.0       # 维护领域用低温度确保准确性
    llm_max_tokens: int = 4096
    
    # ── 嵌入模型 ──
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    
    # ── 向量存储 ──
    vector_store_type: str = "chroma"  # chroma | qdrant
    vector_store_path: str = "./data/vector_store"
    
    # ── RAG ──
    chunk_size: int = 800
    chunk_overlap: int = 120
    retrieval_top_k: int = 10
    hybrid_alpha: float = 0.5          # BM25 vs Vector 权重
    
    # ── Agent ──
    triage_autonomy: str = "low"
    suggest_autonomy: str = "medium"
    compliance_autonomy: str = "high"
    
    @classmethod
    def from_env(cls) -> "AppSettings":
        """从环境变量加载配置"""
        ...
```

---

## 第五部分：数据层 (`data/`)

```
data/
├── knowledge_base/          # RAG 原始文档
│   ├── amm/                 # 飞机维护手册 PDF
│   ├── fim/                 # 故障隔离手册
│   ├── ad/                  # 适航指令
│   ├── sb/                  # 服务通告
│   └── processed/           # 预处理后的文本
├── vector_store/            # 向量持久化
└── app.db                   # SQLite 应用数据（原型阶段）
```

---

## 服务启动流程

```
1. 加载配置       app/config/settings.py
2. 初始化向量存储   app/knowledge/store.py
3. 构建 ATA 索引   app/knowledge/ata_index.py
4. 初始化嵌入器    app/knowledge/embedder.py
5. 初始化检索器    app/knowledge/retriever.py
6. 初始化 Agent    app/agent/orchestrator.py
7. 初始化状态      app/core/state.py
8. 初始化服务      app/core/services/
9. 启动 UI         app/ui/app.py → Flet
```
