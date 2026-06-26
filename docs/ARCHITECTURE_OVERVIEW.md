# TaskSense 整体架构

## 架构原则

```
配置 ↔ 核心 分离：  config/ 只放配置，core/ 只放业务逻辑
前端 ↔ 后端 分离：  ui/ 只管呈现，core/ + agent/ 提供服务
数据 → 状态 → UI：  单向数据流，状态驱动 UI 更新
Agent → 工具 → RAG： Agent 通过工具调用访问知识库和看板状态
```

## 分层架构

```
┌─────────────────────────────────────────────────────────────┐
│                       main.py (入口)                         │
│                  Flet 应用初始化、路由注册                      │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│   app/config/  │   │   app/ui/     │   │   app/core/   │
│   配置层        │   │   表现层       │   │   核心层       │
└───────────────┘   └───────────────┘   └───────────────┘
        │                     │                     │
        │              ┌──────┴──────┐       ┌──────┴──────┐
        │              │             │       │             │
        │         app/ui/      app/ui/  app/core/   app/agent/
        │         components/  pages/   services/   (Agent服务)
        │                                │             │
        │                           app/knowledge/     │
        │                           (RAG知识库)        │
        │                                │             │
        └────────────────────────────────┴─────────────┘
                                         │
                                    data/
                                   (持久化存储)
```

## 层级职责

### 配置层 — `app/config/`

唯一职责：**管理应用运行所需的全部配置项。**

- 不与任何业务逻辑耦合
- 所有可调参数集中管理
- 支持环境变量覆盖
- 配置变更不需要修改业务代码

### 表现层 — `app/ui/`

唯一职责：**将状态渲染为界面，将用户操作转换为事件。**

- 不包含业务逻辑
- 不直接访问数据存储
- 不直接调用外部 API
- 所有数据通过 Service 接口获取
- 所有状态变更通过事件回调通知核心层

### 核心层 — `app/core/`

唯一职责：**实现所有业务逻辑，管理应用状态。**

- 数据模型定义
- 状态管理与变更
- 业务规则校验
- Service 接口定义与实现
- 不依赖 UI 框架

### Agent 层 — `app/agent/`

唯一职责：**封装 AI Agent 的推理与工具调用。**

- Agent 定义（角色、提示词、工具）
- RAG 检索链路
- 工具函数（查询看板、检索文档等）
- 不直接操作 UI

### 知识库层 — `app/knowledge/`

唯一职责：**管理航空维护知识库的构建与检索。**

- 文档预处理与向量化
- 混合检索（BM25 + 向量）
- ATA 章节索引
- 不包含 Agent 逻辑

## 数据流

```
用户操作
    │
    ▼
┌─ UI 层 ──────────────────────────────────────────┐
│  Flet 控件事件 (on_click, on_change, on_drag...)   │
│  调用 PageController 方法                          │
└──────────────────────┬───────────────────────────┘
                       │
                       ▼
┌─ 核心层 ─────────────────────────────────────────┐
│  PageController → Service → StateManager          │
│  1. 校验操作合法性                                  │
│  2. 调用 Service 执行业务逻辑                       │
│  3. 更新 State                                     │
│  4. 触发 UI 刷新回调                                │
└──────────────────────┬───────────────────────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
    ┌──────────┐ ┌──────────┐ ┌──────────┐
    │ Agent 层  │ │知识库层  │ │ 数据层    │
    │ 推理/建议 │ │RAG 检索  │ │持久化     │
    └──────────┘ └──────────┘ └──────────┘
          │            │            │
          └────────────┼────────────┘
                       │
                       ▼
              UI 刷新 (page.update)
```

## 模块依赖规则

```
依赖方向：上层 → 下层（单向）

ui/ ────────────────► core/ ────────────► data/
                           │
                           ├────────────► agent/
                           │                  │
                           └──────────► knowledge/
                                              │
agent/ ───────────────────────────────────────┘

规则：
✅ ui/ 可以 import core/
✅ ui/ 可以 import config/
✅ core/ 可以 import agent/
✅ core/ 可以 import knowledge/
✅ agent/ 可以 import knowledge/
✅ agent/ 可以 import config/
❌ core/ 不可以 import ui/
❌ agent/ 不可以 import ui/
❌ knowledge/ 不可以 import agent/
❌ ui/ 不可以 import data/（通过 core/ 间接访问）
```

## 目录树总览

```
TaskSense/
├── main.py                      # Flet 应用入口
├── pyproject.toml
├── requirements.txt
│
├── app/
│   ├── config/                  # 配置层
│   │   ├── __init__.py
│   │   ├── settings.py          # 全局配置（LLM、向量库、路径等）
│   │   ├── theme.py             # 暗色航空主题定义
│   │   └── constants.py         # 常量（ATA章节、优先级等）
│   │
│   ├── core/                    # 核心层
│   │   ├── __init__.py
│   │   ├── models/              # 数据模型
│   │   │   ├── __init__.py
│   │   │   ├── task.py          # 任务/工单模型
│   │   │   ├── aircraft.py      # 飞机模型
│   │   │   ├── user.py          # 用户/技师模型
│   │   │   └── kanban.py        # 看板状态模型
│   │   ├── state.py             # 全局状态管理器
│   │   ├── services/            # 业务服务
│   │   │   ├── __init__.py
│   │   │   ├── task_service.py  # 任务 CRUD + 业务规则
│   │   │   ├── board_service.py # 看板操作（移动、排序、过滤）
│   │   │   └── report_service.py# 报告生成
│   │   ├── events.py            # 事件总线
│   │   └── validators.py        # 业务校验规则
│   │
│   ├── agent/                   # AI Agent 层
│   │   ├── __init__.py
│   │   ├── triage.py            # Triage Agent（自动分类）
│   │   ├── suggest.py           # Suggest Agent（操作建议）
│   │   ├── compliance.py        # Compliance Agent（AD/SB检查）
│   │   ├── report.py            # Report Agent（报告生成）
│   │   ├── anomaly.py           # Anomaly Agent（异常检测）
│   │   ├── orchestrator.py      # Agent 编排器
│   │   └── tools/               # Agent 工具函数
│   │       ├── __init__.py
│   │       ├── board_tools.py   # 看板操作工具
│   │       ├── search_tools.py  # RAG 搜索工具
│   │       └── report_tools.py  # 报告生成工具
│   │
│   ├── knowledge/               # RAG 知识库层
│   │   ├── __init__.py
│   │   ├── loader.py            # 文档加载器
│   │   ├── chunker.py           # 层级感知分块器
│   │   ├── embedder.py          # 向量化
│   │   ├── store.py             # 向量存储（Chroma/Qdrant）
│   │   ├── retriever.py         # 混合检索器
│   │   └── ata_index.py         # ATA 章节索引
│   │
│   ├── ui/                      # 表现层
│   │   ├── __init__.py
│   │   ├── app.py               # UI 应用初始化 + 路由
│   │   ├── controllers/         # 页面控制器（UI ↔ Core 桥梁）
│   │   │   ├── __init__.py
│   │   │   └── board_controller.py
│   │   ├── pages/               # 页面
│   │   │   ├── __init__.py
│   │   │   ├── board_page.py    # 看板主页
│   │   │   ├── fleet_page.py    # 机队总览页
│   │   │   └── report_page.py   # 报告页
│   │   ├── components/          # 可复用UI组件
│   │   │   ├── __init__.py
│   │   │   ├── kanban_board.py  # 看板主体
│   │   │   ├── kanban_column.py # 看板列
│   │   │   ├── task_card.py     # 任务卡片
│   │   │   ├── side_panel.py    # 右侧详情面板
│   │   │   ├── command_bar.py   # Cmd+K 命令面板
│   │   │   ├── ai_suggestion.py # AI 建议区域
│   │   │   ├── search_bar.py    # 搜索栏
│   │   │   ├── notification.py  # 通知组件
│   │   │   └── fleet_status.py  # 机队状态栏
│   │   └── widgets/             # 基础UI控件
│   │       ├── __init__.py
│   │       ├── badge.py         # 徽章
│   │       ├── ghost_text.py    # 幽灵文本输入
│   │       ├── context_menu.py  # 右键菜单
│   │       └── toast.py         # Toast 通知
│   │
│   └── tools/                   # 通用工具
│       ├── __init__.py
│       ├── logger.py            # 日志
│       └── helpers.py           # 辅助函数
│
├── data/
│   ├── knowledge_base/          # RAG 原始文档
│   └── vector_store/            # 向量存储持久化
│
├── tests/
│   ├── test_core/
│   ├── test_agent/
│   └── test_knowledge/
│
└── docs/
    ├── PROJECT_GOALS.md
    ├── DOMAIN_REFERENCE.md
    ├── UI_DESIGN_INSPIRATION.md
    ├── ARCHITECTURE_OVERVIEW.md
    ├── ARCHITECTURE_FRONTEND.md
    └── ARCHITECTURE_BACKEND.md
```

## 关键设计决策

### 1. 状态管理采用"单一状态树 + 事件驱动"

- 看板状态集中管理在 `core/state.py` 中的 `BoardState`
- UI 通过 `Controller` 发起操作，Controller 调用 Service 更新 State
- State 更新后通知 UI 刷新
- 避免 UI 组件间直接传递状态

### 2. Agent 通过工具函数访问系统

- Agent 不直接操作 State 或 UI
- Agent 通过 Tool 接口访问看板数据、RAG 检索
- 遵循 LangChain Tool 规范
- Agent 返回结构化结果，由 Service 决定如何应用

### 3. Flet 作为统一 UI 框架

- 原型阶段 Flet 覆盖桌面端和 Web 端
- UI 组件封装在 `app/ui/` 中，与 Flet 框架松耦合
- 后续如需迁移前端框架，只需替换 `app/ui/` 层

### 4. 知识库层的独立性

- 文档加载、分块、向量化、检索各自独立
- 支持切换向量数据库（Chroma ↔ Qdrant）只改配置
- 检索器返回结构化结果，不绑定 Agent 或 UI
