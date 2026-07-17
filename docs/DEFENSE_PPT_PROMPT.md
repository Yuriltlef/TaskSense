# TaskSense 毕业答辩 PPT 生成提示词

> 将以下内容交给 AI（如 Claude、ChatGPT），生成一份 39 页左右的毕业答辩 PPT Markdown 文稿。每页用 `---` 分隔，页首标注 `## 第N页 · 标题`。

---

## 一、项目基本信息

- **项目名称**：TaskSense — 航空维护智能看板系统
- **技术栈**：Python 3.11+ / Flet 0.28.3 (Flutter-based UI) / SQLite / ChromaDB / BGE-M3 嵌入模型 / OpenAI-compatible LLM
- **代码规模**：~15,000 行 Python，324 个测试用例全部通过
- **开发周期**：约 4 周，累计 60+ 次提交
- **应用领域**：民航飞机维护任务管理 (MRO — Maintenance, Repair & Overhaul)

---

## 二、PPT 结构要求（共 40 页）

### 第一部分：封面与目录（3 页）

**第 1 页 · 封面**
- 项目名称：TaskSense — 航空维护智能看板系统
- 副标题：基于 RAG + LLM Agent 的智能航空维护管理平台
- 作者 / 导师 / 日期（2026 年 7 月）

**第 2 页 · 目录**
- 列出九大板块：应用价值、技术路线、软件架构、功能介绍、AI Agent 工具详解、知识库构建详解、核心代码解读、总结展望

**第 3 页 · 项目背景与痛点分析**
- 民航维护任务管理痛点：
  - 工卡种类多（ATA 100 规范 ~70+ 章节），排故/检查/勤务/拆装/测试/修理 6 大类
  - MEL 延期分类复杂（AOG 立即停飞 / Cat A 当日 / Cat B 3天 / Cat C 10天 / Cat D 120天）
  - 纸质工卡流转慢，状态追踪困难
  - 维修知识分散在 AMM/SRM/IPC 等多本手册中，查阅效率低
  - 合规审查依赖人工，易遗漏 AD/SB/RII 等强制要求

---

### 第二部分：应用价值（4 页）

**第 4 页 · 应用场景**
- 目标用户：航线维修控制中心 (MCC)、维修计划工程师、质检员、放行人员
- 典型场景：
  1. 机组报告故障 → 创建排故工卡 → 看板追踪 → AI 辅助分类排程 → 执行 → 验收 → 归档
  2. 定检计划下发 → 批量生成任务 → 自动排程 → 员工接单 → 阻塞处理 → 提交审核
  3. AOG 紧急排故 → 高优先级可视 → 跨部门协同 → AI 知识库即时检索

**第 5 页 · 核心价值主张**
- **效率提升**：看板拖拽 + 右键菜单，状态流转一键完成；AI 批量生成/分类/排程，减少 70% 手工录入
- **知识赋能**：航空维修 PDF 知识库 + 混合检索 (语义 + BM25 + RRF)，秒级定位标准工卡
- **合规保障**：状态转换矩阵硬约束 + AI 合规审查（6 维度：完整性/安全/排程/文档/零件/历史）
- **协同实时**：主应用 + 3 个子进程窗口（员工工作台/甘特图/任务看板），TCP Socket 实时同步
- **可追溯**：操作审计日志 + 撤销/重做 (Command 模式，200 步栈)

**第 6 页 · 领域知识覆盖**
- ATA 100 规范：5 大类 (通用/系统/结构/螺旋桨/动力装置)，70+ 章节目录
- 优先级体系：AOG → Cat A → Cat B → Cat C → Cat D (MEL 延期时限)
- 9 列看板工作流：待处理 → 已分类 → 已排程 → 就绪 → 执行中 → 验收中 → 阻塞(可回退) → 已完成 → 已归档
- 6 大任务类型：排故 / 检查 / 勤务 / 拆装 / 测试 / 修理
- 合规要素：AD (适航指令) / SB (服务通告) / RII (必检项) / MEL (最低设备清单)

**第 7 页 · 与同类系统对比**
- vs 通用看板 (Trello/Notion)：领域专业化（ATA/优先级/合规字段），AI 深度集成
- vs 企业 MRO 系统 (AMOS/TRAX)：轻量级桌面应用，安装即用，无服务器依赖
- vs 纯手工管理：状态可视化、自动流转、知识检索

---

### 第三部分：技术路线（4 页）

**第 8 页 · 整体技术路线图**
- Phase 1：核心数据模型 + 看板 UI + 拖拽交互（Flet 组件树）
- Phase 2：AI Agent 集成（LLM + 13 工具 + 提示词系统 + 幽灵卡提案）
- Phase 3：RAG 知识库（PDF 解析 → 自适应分块 → BGE-M3 嵌入 → ChromaDB → 混合检索）
- Phase 4：多进程架构（员工工作台 / 甘特图 / 任务看板）+ TCP Socket IPC
- Phase 5：持久化 (JSON → SQLite) + 撤销/重做 + 审计日志 + 后台调度器

**第 9 页 · 关键技术选型**
| 层级 | 技术 | 选型理由 |
|------|------|---------|
| UI 框架 | Flet 0.28.3 | Python 生态、Flutter 渲染、跨平台 |
| 状态管理 | 自研 AppState + RLock | 多线程安全、订阅/通知模式 |
| 数据库 | SQLite | 嵌入式、零配置、适合桌面应用 |
| 向量存储 | ChromaDB | 轻量级、Python 原生、支持多集合 |
| 嵌入模型 | BGE-M3 (本地) | 中文友好、1024 维、离线可用 |
| LLM | OpenAI-compatible API | 灵活切换 (DeepSeek/Anthropic) |
| IPC | TCP Socket + JSON Lines | 子进程实时通信、低延迟 |
| 测试 | pytest | 324 用例、覆盖核心/边界/服务/配置 |

**第 10 页 · 开发流程**
- 敏捷迭代：需求分析 → 原型设计 → 迭代开发 → 代码审查 → 重构 → 测试
- 重构里程碑：board_page.py 3538 行 → 1665 行 (-53%)，拆分出 17 个独立模块
- 代码质量：消除 80+ print 语句 → 结构化日志；取消流程覆盖 9 条退出路径

**第 11 页 · AI Agent 技术路线**
- LLM 不可用时的离线降级策略（规则匹配 + 模板生成）
- 三层任务锁防护：system.md 全局规则 / task_guard.md 跨 Session 注入 / 工具提示词约束
- 幽灵卡提案模式：AI 输出不直接写入，以半透明卡片呈现，用户确认后生效
- 内联补全两层架构：关键词匹配 (<1ms) + LLM Agent (600ms 防抖)

---

### 第四部分：软件架构（5 页）

**第 12 页 · 五层架构总览**
```
┌─────────────────────────────────────────┐
│          UI 层 (Flet + 组件树)            │
│  Page → KanbanBoard → Column → TaskCard │
│  Panel → Dialog → Widget → Overlay       │
├─────────────────────────────────────────┤
│        服务层 (Bridge / Coordinator)       │
│  BoardRenderer  AgentService  AICommands │
│  ProposalHandler  CancelCoordinator      │
├─────────────────────────────────────────┤
│         核心层 (纯业务逻辑)                │
│  AppState  TaskService  BoardService     │
│  EventBus  Validators  UndoManager       │
│  SocketServer  PersistenceService        │
├─────────────────────────────────────────┤
│         Agent 层 (LLM + RAG)             │
│  Orchestrator  LLMClient  Conversation   │
│  13 Tools  KnowledgePipeline  Retriever  │
├─────────────────────────────────────────┤
│         数据层 (Models + Storage)         │
│  Task  Aircraft  Kanban  LogEntry        │
│  SQLite  ChromaDB  JSON (settings)       │
└─────────────────────────────────────────┘
```

**第 13 页 · 单一状态树 + 订阅模式**
- `AppState` 全局单例：`_tasks` / `_task_order` / `_columns` / `_aircraft`，`threading.RLock()` 保护
- 订阅/通知：UI 组件通过 `state.subscribe(listener)` 注册，状态变更自动 `_notify()`
- EventBus：10 种事件类型 (TASK_CREATED/UPDATED/MOVED/DELETED, FILTER_CHANGED…)
- 序列化：`to_dict()` / `load_from_dict()` 完整导出/恢复

**第 14 页 · 组件树与 Controller Bridge 模式**
- Flet 组件层次：
  ```
  Stack
    Container(main_content)
      Column
        FleetStatusBar
        Row
          KanbanBoard (Column × N, DragTarget + Draggable 卡片)
          GestureDetector (面板拖动)
          SidePanel (任务详情)
          AIChatPanel (LLM 对话)
        BottomStatusBar
    Container(dimmer_slot)
  ```
- BoardController 作为 UI ↔ Core 桥梁：持有选中状态，订阅 state 变更，封装 7 个操作指令
- 拖拽架构：每张卡片 = DragTarget(Draggable(GestureDetector(TaskCard)))，卡片级 DropTarget 避免 Flet 0.28.3 已知 Bug

**第 15 页 · 多进程 + Socket IPC 架构**
- 主进程：TaskSenseApp (看板 + AI + 设置)
- 3 个子进程窗口（串行 spawn 队列，防 Flet 引擎初始化冲突）：
  - EmployeeWorkbench：员工登录 → 任务列表 → 接单/阻塞/提交
  - GanttChart：时间线视图，已排程/进行中任务
  - TaskBoard：只读 6 列看板概览
- 通信协议：TCP `127.0.0.1:random_port`，JSON 行协议 (每行 `{JSON}\n`)
- Hash 轮询：子进程每秒请求 `hash`，仅变更时拉取全量 state
- 联动关闭：TCP 断连 → 子进程窗口自动关闭

**第 16 页 · 关键设计模式**
| 模式 | 应用 | 代码位置 |
|------|------|---------|
| 单例 | state, agent, event_bus, socket_server, theme | 模块级全局变量 |
| 观察者 | AppState.subscribe / EventBus.on | state.py / events.py |
| 命令 | UndoManager (undo/redo 闭包栈) | undo_manager.py |
| 策略 | ProposalHandler (按类型路由 accept/reject) | proposal_handler.py |
| 桥接 | BoardController, AgentService | controllers / services |
| 模板方法 | 弹窗三段式 (header + body + footer) | dialog_builder.py |
| 两层 AI | 关键词 (<1ms) + LLM (600ms 防抖) | ai_completion.py |

---

### 第五部分：航空知识库构建详解（4 页）

**第 17 页 · 知识库流水线架构**
- 整体数据流：
  ```
  PDF 文档 (AMM/FIM/AD/SB/教材)
    → PDFLoader (pypdf 提取 + 页码追踪)
    → TextChunker (自适应分块)
    → Embedder (BGE-M3 嵌入, 1024维)
    → VectorStore (ChromaDB 多 Collection)
    → HybridRetriever (语义 + BM25 + RRF 融合)
  ```
- 冷热分离双 Collection 设计：
  | Collection | 用途 | 更新策略 |
  |------|------|------|
  | kb_static | PDF 知识库（AMM/FIM/AD/SB/教材） | 构建一次，force=True 重建 |
  | kb_live | 任务操作日志（增量） | 每次操作追加，实时可检索 |
- 配置入口：`settings.json` → `rag` 节点 (chunk_size=500, chunk_overlap=80, top_k=10)
- 构建命令：`python scripts/build_kb.py embed --force`

**第 18 页 · PDF 解析 + 自适应分块**
- PDFLoader：pypdf 逐页提取文本 + 页码追踪 (`page_starts` 列表)
  - 预处理：修复 PDF 断行（非句末标点结尾 → 合并）、规范化空白
  - 页码标记注入：`[[PAGE:N]]` 标记 → 分块后提取页码范围
  - 文档类型自动推断：12 条正则规则覆盖 AMM/FIM/AD/AC/AMT_Handbook/SB/Regulation/IPC/SRM/WDM/MEL
- TextChunker 三级分块策略（按优先级降级）：
  1. **ATA 章节切分**：正则匹配 `ATA 32-41-03` / `Chapter 72` 等模式 → 验证两码前缀（对照 25 个有效 ATA 前缀白名单） → ≥3 个不同 ATA 标签才确认为 ATA 结构化文档
  2. **通用标题切分**：Chapter/Section/Part + 中文"第X章/节/部分" + 编号标题 + 全大写短行
  3. **段落边界切分**：双换行段落 → 合并相邻短段（< 200 字符）
- Token 感知分块：`max_chars = chunk_size / 0.55`（BGE-m3 ~1.8 tokens/中文字符），句子边界尊重，重叠窗口 (80 tokens)
- 后处理：过滤过小块 (< 100 字符) + 合并相邻短节段

**第 19 页 · BGE-M3 嵌入 + ChromaDB 存储**
- Embedder (`app/knowledge/embedder.py`)：
  - 模型：`BAAI/bge-m3`（本地加载，1024 维向量，多语言）
  - 查询前缀：`"航空维护查询："` 自动 prepend（提升检索相关性）
  - 设备：自动检测 CUDA/CPU，`model_cache` 目录缓存
  - 后台预加载：`preload.py` 在应用启动时异步加载模型
- VectorStore (`app/knowledge/store.py`)：
  - 后端：ChromaDB（嵌入式，无服务器依赖）
  - 多 Collection 支持：`kb_static` + `kb_live`
  - 操作：`add_chunks()` / `search()` / `count()` / `clear()` / `get_all_chunks()` / `get_collection()`
  - 元数据过滤：支持 ChromaDB `where` 子句（ATA 章节前缀、文档类型）

**第 20 页 · 混合检索：BM25 + 语义 + RRF + 重排序**
- 三路检索融合架构：
  ```
  查询 "B737 主起落架减震支柱勤务"
    ├── 语义检索：BGE-M3 embedding → ChromaDB ANN 搜索 (top_k*2)
    ├── BM25 关键词：混合中英文 Tokenize → BM25 索引搜索 (top_k*2)
    │     - 英文：3+ 字母/数字词 → 小写
    │     - 中文：逐字 bigram → 如 ["主起", "起落", "落架", ...]
    │     - k1=1.5, b=0.75 (标准 BM25 参数)
    └── RRF 融合：score = Σ 1/(60 + rank_i) → 归一化到 [0,1]
  ```
- 查询扩展：结果 < 3 条 → ATA 编号剥离重试 / 短查询补充 "aviation maintenance" 前缀
- 相关性阈值：`min_score = 0.30`（可配置）
- Cross-Encoder 重排序（可选）：
  - 模型：`BAAI/bge-reranker-v2-m3`
  - 触发：`settings.json` → `rag.rerank_enabled = true`
  - 延迟：~50ms/对，适合 top-20 候选重排
- 增量 RAG（`search_operation_log`）：
  - 操作日志 SQLite 全文搜索（`log_service.search_logs()`）
  - 按时间倒序返回最近操作记录
  - 用于 Agent 了解历史类似任务的处理方式
- BM25 缓存管理：
  - 索引按 collection 缓存 → 检测 `collection.count()` 变化自动重建
  - `invalidate_bm25()` 在 `add_chunks()` 后调用

---

### 第六部分：全部功能介绍（8 页）

**第 21 页 · 看板主页 (Kanban Board)**
- 9 列工作流：待处理 / 已分类 / 已排程 / 就绪 / 执行中 / 验收中 / 阻塞中 / 已完成 / 已归档
- WIP 限制可视化：triage=10, ready=20, in_progress=15, inspection=15, parts_hold=10，超出变红
- 拖拽排序 + 列间移动：ALLOWED_DRAG_TRANSITIONS 限制（仅 backlog↔triage↔scheduled 允许拖拽）
- 右键菜单：9 列不同菜单项（编辑/优先级/排程/分类/审核/搜索/解释/阻塞/删除）
- 视图筛选：8 字段 + 4 日期范围 + 搜索查询

**第 22 页 · 任务卡片 (TaskCard)**
- L1 卡片信息：优先级色条 (5 色) + ATA 章节标签 + 任务类型图标 + 标题 + 飞机注册号 + 负责人 + 工时 + 到期倒计时
- L2 悬停展开：卡片放大 `scale 1.01`，蓝色边框，显示 RII 标签 / 阻塞原因 / 清单进度条
- L3 详情面板 (Side Panel)：全部字段、清单勾选、状态历史时间线、AI 建议区、提交审核区
- 特殊状态：幽灵卡 (45% opacity + 虚线边框 + 接受/拒绝按钮)、高亮卡 (蓝色/橙色边框脉冲)

**第 23 页 · 任务生命周期管理**
- 创建：弹出表单 (GhostTextField AI 补全，员工自动补全，日期选择器，优先级选择器)
- 编辑：状态感知字段锁定（backlog 全部可编辑 → in_progress 仅日志可写 → completed 全部只读）
- 流转：拖拽 / 右键菜单 / AI 命令 / 后台调度器 四种方式
- 阻塞/解除阻塞：ready/in_progress 可阻塞至 parts_hold，必须填写原因
- 提交验收：交接班日志 + 实际工时 → inspection → AI 审核 → completed/backlog
- 删除/归档：completed → archived (不可逆)

**第 24 页 · AI 对话面板 (AIChatPanel)**
- IDE 风格侧栏（VS Code 启发）：最小宽 380px，可拖拽调整至 800px
- 聊天气泡：用户消息 / AI 回复 (Markdown 渲染) / 工具调用折叠 / 错误提示
- Normal / Strict 双模式：Normal = KB 优先 + 专业补充；Strict = 仅 KB 内容 + 精确引用
- 任务进度卡片：显示 AI 正在处理的任务，含进度条和状态文本
- 幽灵提案操作：单卡接受/拒绝 + 全部接受/全部拒绝 按钮
- 底部工具栏：模型选择器 / 深度设置 / 发送/停止按钮

**第 25 页 · 7 大 AI 命令**
| 命令 | 功能 | 输入 | 输出 |
|------|------|------|------|
| `/outline` | 生成大纲 | 自然语言描述 | 结构化步骤 |
| `/gen` | 生成任务 | 大纲确认 | 批量幽灵卡 |
| `/classify` | 自动分类 | 扫描 backlog | 设置优先级 + 移至 triage |
| `/schedule` | 自动排程 | 已分类任务 | 分配日期/员工 + 移至 scheduled |
| `/acceptance` | 自动验收 | 扫描 inspection | 逐卡审核 → 幽灵卡(建议通过/拒绝) |
| `/report` | 生成报告 | 看板数据 | 日报文本 |
| `/review` | 任务审核 | 指定任务 | 6 维度合规报告 (JSON) |

**第 26 页 · AI 内联补全 + 右键 AI 工具**
- 内联补全 (GhostTextField)：
  - 关键词层：200+ 关键词 → ATA 章节 / 任务类型映射 (<1ms)
  - LLM 层：600ms 防抖 → 调用 Agent → 返回标题/描述/类型/ATA/区域建议
- 右键 AI 工具 (5 项)：
  - 解释任务 (explain_task) / 搜索知识库 (search_docs) / 分类单个 (classify_single) / 排程单个 (schedule_single) / 审核单个 (review_single)
  - 统一入口 `_run_single_task_ai()`，自动检测 LLM 是否调用了工具，失败自动重试

**第 27 页 · 命令面板 (Ctrl+K) + 快捷键**
- Ctrl+K 命令面板：13 个命令，分 4 组 (面板 / AI 工具 / 命令 / 导航)，支持搜索过滤
- 键盘快捷键：
  - Ctrl+Z / Ctrl+Y：撤销 / 重做 (Command 模式，200 步栈，支持操作分组)
  - Ctrl+Shift+Z：重做 (备用)
  - Escape：关闭面板 / 右键菜单 / 取消 AI / 关闭弹窗
- 自定义标题栏：窗口拖拽区域 + 搜索框 + AI 工具下拉菜单 + 窗口控制按钮

**第 28 页 · 设置面板 + 子进程窗口 + 后台调度**
- 设置面板 (4 标签页)：
  - LLM/API：API Key、Base URL、Model、Temperature、Max Tokens、Timeout
  - RAG 知识库：知识库路径、分块大小/重叠、Top-K、混合检索权重
  - 界面与主题：语言、缩放、字体大小、自动保存间隔
  - Agent 行为：自主权限级别、幽灵卡默认行为、离线降级开关
- 3 个子进程窗口：
  - 员工工作台：选择身份 → 查看指派任务 → 接单 / 阻塞 / 提交
  - 甘特图：时间线视图，优先级色编码，每天列宽自适应
  - 任务看板：只读 6 列概览 (已排程→就绪→执行中→验收中→阻塞中→已完成)
- 后台调度器 (BoardScheduler)：每 10s tick，自动 scheduled→ready (到达计划时间)，逾期检测

---

### 第七部分：AI Agent 功能工具详解（5 页）

**第 29 页 · 13 个 Agent 工具全景图**
- 工具分类（4 大类）：
  | 类别 | 数量 | 工具列表 | 权限 |
  |------|:--:|------|:--:|
  | 知识检索 | 3 | search_knowledge_base, lookup_ata_chapter, search_operation_log | 只读 |
  | 看板查询 | 5 | get_board_summary, get_task_detail, search_related_tasks, search_employees, search_tasks_by_title | 只读 |
  | 任务写入 | 4 | create_task, update_task, classify_task, schedule_task | 需确认 |
  | 审核/状态 | 2 | acceptance_review, get_active_task | 需确认 |
- 13 个工具统一注册在 `ToolExecutor._TOOLS` 字典中，LLM 通过 Markdown 代码块调用
- 写入工具均输出"幽灵卡"（ai_proposed=True），需用户确认后才生效
- update_task 设有字段白名单 `_UPDATE_ALLOWED`（19 个安全字段），禁止 LLM 直接修改 status/priority

**第 30 页 · 工具调用协议与解析**
- LLM 通过 Markdown 代码块格式请求工具调用：
  ```
  ```tool
  search_knowledge_base
  query=B737 主起落架减震支柱勤务程序
  top_k=5
  doc_type=amm
  ```\```
- 解析器 `_parse_tool_calls()`：正则匹配 ` ```tool ... ``` ` 块 → 按行解析 `key=value` → 提取 tool_name + params dict
- 工具执行流程：
  ```
  ToolExecutor.execute(tool_name, params)
    → _TOOLS 注册表查找 → 动态 __import__ 模块
    → 内置工具 (_kb/_ata/_oplog) 直接调用
    → 外部工具 (board_tools/write_tools) invoke(params)
    → 返回结果文本 → 追加到 LLM messages
  ```
- 关键设计：
  - 写入工具返回 `confirm_needed: True` 标记 → UI 层渲染为幽灵卡
  - 白名单过滤：`update_task` 拒绝修改 status/priority/ai_* 等关键字段
  - 日期类型转换：LLM 传字符串 `"2026-07-15 08:00"` → `datetime.fromisoformat()` 自动转换

**第 31 页 · 7 大 AI 命令详解（上）**
- `/outline` 生成大纲：
  - 输入：自然语言描述（如"B737NG A检工卡"）
  - 处理：`generate_outline` 提示词 → LLM 调用 `search_knowledge_base` 检索标准工卡 → 输出结构化步骤列表
  - 交互模式：`generate_outline_interactive.md` 两阶段确认
- `/gen` 生成任务：
  - 输入：确认后的大纲
  - 处理：`generate_tasks` 提示词 → LLM 调用 `create_task` 工具批量创建 → 每个任务标记 `ai_proposed=True`
  - 输出：批量幽灵卡，显示在 backlog 列，带接受/拒绝按钮
- `/classify` 自动分类：
  - 输入：扫描 backlog 列所有待分类任务
  - 处理：LLM 逐个分析标题/描述 → 调用 `classify_task` 设置优先级 (aog/cat_a/b/c/d)
  - 输出：幽灵卡显示建议优先级，接受→移至 triage，拒绝→保持 backlog
- `/schedule` 自动排程：
  - 输入：triage 列已分类任务
  - 处理：LLM 分析 ATA 章节/工时 → 调用 `schedule_task` 分配日期和员工
  - 输出：幽灵卡显示排程建议 (planned_start/end + employee)，接受→移至 scheduled

**第 32 页 · 7 大 AI 命令详解（下）+ 右键 AI 工具**
- `/acceptance` 自动验收：
  - 输入：扫描 inspection 列
  - 处理：LLM 逐卡调用 `acceptance_review(task_id, recommendation, reason)`
  - recommendation = "approve" (同意→completed) 或 "reject" (驳回→backlog)
  - 输出：幽灵卡显示审核结论 + 理由
- `/report` 生成报告：
  - 输入：看板统计数据 (get_board_summary)
  - 处理：模板 + 实时数据 → 日报文本 (机队状态 + 任务概况 + 逾期/AOG 汇总)
  - 离线可用：纯规则生成，不依赖 LLM
- `/review` 任务审核：
  - 输入：指定任务 ID
  - 处理：`task_review.md` 提示词 → 6 维度合规审计（完整性/安全性/排程合理性/文档完整性/零件状态/历史记录）
  - 分批处理：每批 6 个任务，增量 UI 更新
  - 离线降级：`_local_task_review()` 7 条本地规则检查
- 右键 AI 工具（5 项，统一入口 `_run_single_task_ai()`）：
  | 工具 | 功能 | 提示词 |
  |------|------|------|
  | 解释任务 | 用知识库解释任务内容 | explain_task.md |
  | 搜索知识库 | 按标题/ATA 检索相关文档 | search_docs.md |
  | 分类单个 | 对单个任务建议优先级 | classify_single.md |
  | 排程单个 | 对单个任务建议排程 | schedule_single.md |
  | 审核单个 | 对单个任务合规审查 | review_single.md |
  - 自动重试：检测 LLM 是否调用了工具，未调用则重试一次

**第 33 页 · 提示词工程 + 任务锁 + 幽灵卡生命周期**
- 提示词体系（20 个 .md 文件）：
  ```
  system.md (角色 + 能力边界)
    ├── tool_use.md (13 工具完整文档 + 调用格式)
    ├── normal_mode.md (KB 优先 + 专业知识补充)
    ├── strict_mode.md (仅 KB 内容 + 精确引用)
    └── task_guard.md (任务锁：当前正在执行 X 任务)
  ```
  - 运行时组装：`_build_system_prompt(strict)` → system + tool_use + mode → 注入 task_guard (条件)
- 三层任务锁防护：
  1. system.md 全局规则："你一次只处理一个任务"
  2. task_guard.md：`ActiveTaskRegistry.inject_context()` 检测 session 不匹配 → 注入锁提示
  3. 工具提示词：`get_active_task` 工具返回当前锁定任务，写入工具检查 `session_id`
- 幽灵卡生命周期：
  ```
  AI 调用写工具 → ai_proposed=True → EventBus.AI_PROPOSAL_CREATED
    → BoardRenderer 注入幽灵卡 (45% opacity + 接受/拒绝按钮)
    → ProposalHandler.accept()  → 根据 proposal_type 执行:
         new_task: 清除 ai_proposed 标志
         classify: 设置优先级 + move_task → triage
         schedule: 更新字段 + move_task → scheduled
         acceptance: approve → completed / reject → backlog
    → ProposalHandler.reject() → 清除标志或删除任务
  ```

---

### 第八部分：核心功能代码解读（6 页）

**第 34 页 · Agent 编排器：LLM ↔ Tool 循环**
- 文件：`app/agent/orchestrator.py` (520 行)
- 核心流程：
  ```
  AgentOrchestrator.ask(question, session_id, strict, cancel_event)
    → inject_context() 注入任务锁
    → _agent_loop()  ← 最多 3 轮工具调用
       1. _chat_with_cancel()  ← 可中断 LLM 调用 (ThreadPool + 150ms 轮询)
       2. _parse_tool_calls()  ← 正则解析 ```tool 块
       3. ToolExecutor.execute()  ← 13 工具动态分派
       4. 工具结果追加到 messages
       5. 无工具调用 → 返回最终回答
  ```
- 关键代码解读：
  - `_chat_with_cancel`：`ThreadPoolExecutor` 异步执行 HTTP 请求，主线程每 150ms 检查 `cancel_event`
  - `ToolExecutor._TOOLS`：工具注册表 → 动态 `__import__` 模块
  - `MAX_TOOL_ROUNDS = 3`：超限后强制 LLM 输出最终答案

**第 35 页 · 全局状态管理器：线程安全 + 撤销/重做**
- 文件：`app/core/state.py` (696 行)
- `AppState` 核心设计：
  - `threading.RLock()` 保护所有数据结构
  - `create_task()` → 生成 UUID + 工卡号 → 插入 backlog 首位 → 记录日志 + 事件 + 撤销
  - `move_task()` → 状态转换验证 → 移除+插入 → transition_to() → 撤销记录 (闭包)
  - `_record_undo_*()` → undo/redo 闭包工厂 → `undo_manager.push(description, undo_fn, redo_fn)`
- `_apply_filters()`：8 字段 + 4 日期范围 + 模糊搜索，链式过滤
- `get_fleet_summary()`：从实时任务统计机队状态（运行/维修/AOG），合并存储飞机 + 任务引用的注册号

**第 36 页 · Socket IPC：主-子进程通信**
- 文件：`app/core/services/socket_server.py` (332 行)
- Server 端 (主进程)：
  - 绑定 `127.0.0.1:0` (随机端口) → 端口写入 `data/server_port.txt`
  - `_accept_loop`：后台线程接受连接，每个客户端独立线程 `_handle_client`
  - 协议：`{action, params}` → `dispatch()` → 6 种 action → 返回 `{ok, data/error}`
  - Hash 检测：`_state_hash()` = SHA-256(json.dumps(state))[:16]
- Client 端 (子进程)：
  - 读取 `server_port.txt` → `connect()` → `start_polling(1s, on_change)`
  - 后台线程每 1s 请求 hash → 变更时调用 `on_change()` 拉取全量
- 关键设计：`send_command()` 发命令后直接返回新 state，不额外轮询

**第 37 页 · RAG 混合检索：BM25 + 语义 + RRF**
- 文件：`app/knowledge/retriever.py`
- 架构：`HybridRetriever` 融合三路检索
  - 语义检索：BGE-M3 嵌入 + ChromaDB 向量搜索 (query 前缀 "航空维护查询：")
  - BM25 关键词：中文分词 + IDF 加权
  - 层级扩展：按 ATA 章节目录层级关系扩展相关文档
  - RRF (Reciprocal Rank Fusion)：`score = Σ 1/(k + rank_i)` (k=60)
- 增量 RAG：`search_operation_log` 工具 → 操作日志 SQLite 全文搜索
- 自适应分块：根据 PDF 标题层级动态决定 chunk 大小 (256-1024 tokens)

**第 38 页 · 撤销/重做：Command 模式实现**
- 文件：`app/core/services/undo_manager.py` (219 行)
- `UndoManager` 设计：
  - `_Command` 数据类：`description + undo_fn + redo_fn + group_id`
  - 双栈：`_undo_stack` (最多 200) + `_redo_stack`
  - `push()`：推入 undo 栈，清空 redo 栈 (新操作使重做历史失效)
  - `begin_group()` / `end_group()`：批量 AI 操作的事务性撤销
  - `_replaying` 标志：防止 undo/redo 执行时重复记录
- 在 AppState 中的集成：
  - `_record_undo_move`：捕获 from_col/old_idx/to_col/new_idx，生成反向 move 闭包
  - `_record_undo_create`：undo = delete_task；redo = no-op (不可重做)
  - `_record_undo_delete`：snapshot → `Task.from_dict()` 恢复

---

### 第九部分：总结与展望（1 页）

**第 39 页 · 总结与展望**
- 已完成：
  - ✅ 完整 9 列看板 + 拖拽 + WIP 限制 + 筛选
  - ✅ 40+ 字段 Task 模型 + 完整生命周期
  - ✅ 13 工具 AI Agent + 7 大命令 + 幽灵卡提案
  - ✅ RAG 知识库 (混合检索 + 增量索引)
  - ✅ 多进程架构 (Socket IPC + 实时同步)
  - ✅ SQLite 持久化 + 撤销/重做 + 审计日志
  - ✅ 324 测试全部通过
- 展望：
  - 周期性合规审查自动化
  - 依赖图可视化 (任务父子/阻塞关系)
  - PyInstaller 打包分发
  - 多语言支持 (中/英)
  - 云同步 (多 MCC 站点协作)

---

## 三、PPT 制作要求

### 样式要求
- 深色主题（#080808 背景，#0e0e0e 面板，#c8c8c8 文字）
- 主色调：#5294e2 (蓝色)
- 字体：HarmonyOS Sans SC (中文) + Consolas (代码)
- 每页标题居中，内容左对齐
- 代码页使用深色背景的代码块

### 内容要求
- "功能介绍" 部分尽可能配截图或架构图
- "核心代码解读" 部分用伪代码 + 关键注释，不可直接粘贴大段源码
- 每页内容不宜过多，标题 + 3-5 个要点最佳
- 页与页之间逻辑衔接清晰

### 输出格式
- 纯 Markdown 文本
- 每页用 `---` 分隔
- 页首标注 `## 第N页 · 标题`
- 代码块使用 ` ```python ` 包裹
- 表格使用 Markdown 表格语法
