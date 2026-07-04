# TaskSense — 航空维护智能看板系统

基于 Flet 0.28.3 的桌面应用，集成 RAG 知识库 + LLM Agent 的航空维护管理工具。

## 项目架构

```
TaskSense/
├── main.py                          # 入口：模型缓存 + 日志清理 + 预加载 + 启动
├── settings.json                    # 运行时配置（LLM/RAG/UI/Agent）
├── pyproject.toml
├── requirements.txt
│
├── app/
│   ├── config/
│   │   ├── theme.py                 # 暗色主题 + SCALE 缩放
│   │   ├── settings_manager.py      # settings.json 持久化（含 from_env）
│   │   ├── settings.py              # AppSettings dataclass（测试用）
│   │   ├── constants.py             # 航空领域常量（ATA/Priority/列定义/状态转换）
│   │   └── ata_keywords.py          # ATA 章节关键词推测（中/英文）
│   │
│   ├── core/
│   │   ├── state.py                 # 全局状态树（任务/飞机/看板，含验证守卫）
│   │   ├── events.py                # EventBus 发布/订阅
│   │   ├── validators.py            # 业务规则校验（WIP/状态转换/字段格式）
│   │   ├── logging.py               # 结构化日志（控制台+文件双通道）
│   │   ├── log_manager.py           # 日志自动清理（启动时）
│   │   ├── models/
│   │   │   ├── task.py              # Task/Priority/TaskStatus（含 to_submission_context）
│   │   │   ├── aircraft.py          # Aircraft/AircraftStatus
│   │   │   ├── kanban.py            # BoardState/ColumnConfig/FilterState
│   │   │   └── log_entry.py         # LogEntry 审计日志
│   │   └── services/
│   │       ├── board_service.py     # 看板查询/筛选/统计
│   │       ├── task_service.py      # 任务 CRUD + 阻塞/取消阻塞
│   │       ├── employee_service.py  # 员工数据（20人JSON）
│   │       ├── persistence_service.py # 看板状态持久化（5s防抖）
│   │       ├── log_service.py       # 审计日志（debounce持久化）
│   │       └── board_scheduler.py   # 后台自动流转（scheduled→ready→in_progress）
│   │
│   ├── agent/
│   │   ├── orchestrator.py          # Agent编排器（工具调用+多轮对话+可中断LLM）
│   │   ├── conversation.py          # 多轮对话会话管理
│   │   ├── llm_client.py            # OpenAI-compatible LLM 客户端
│   │   ├── active_task.py           # 活跃任务锁（防Agent偏离）
│   │   ├── json_extractor.py        # 4级JSON解析器
│   │   ├── preload.py               # 启动预加载（嵌入模型+KB预热）
│   │   ├── prompts/                 # 19个提示词文件
│   │   │   ├── system.md / tool_use.md / strict_mode.md / normal_mode.md
│   │   │   ├── task_guard.md        # 任务守卫（防止跨任务干扰）
│   │   │   ├── classify_single.md / schedule_single.md / review_single.md
│   │   │   ├── auto_classify.md / auto_schedule.md / auto_acceptance.md
│   │   │   ├── generate_outline.md / generate_tasks.md / generate_reports.md
│   │   │   ├── explain_task.md / search_docs.md / task_review.md
│   │   │   └── review_submission.md / generate_outline_interactive.md
│   │   └── tools/
│   │       ├── search_tools.py      # RAG 检索
│   │       ├── board_tools.py       # 看板查询
│   │       ├── write_tools.py       # 写工具（创建/更新/分类/排程/验收，含白名单）
│   │       └── task_state_tools.py  # 任务状态查询
│   │
│   ├── knowledge/
│   │   ├── pipeline.py              # 知识库流水线（构建/增量/检索）
│   │   ├── chunker.py               # 内容自适应文本分块
│   │   ├── embedder.py              # BGE-m3 向量化
│   │   ├── loader.py                # PDF 加载器
│   │   ├── store.py                 # ChromaDB 向量存储
│   │   ├── retriever.py             # 混合检索器（语义+BM25+RRF）
│   │   └── cache_utils.py           # 模型缓存设置工具
│   │
│   └── ui/
│       ├── app.py                   # 主窗口（标题栏/布局/窗口操作）
│       ├── pages/
│       │   ├── board_page.py        # 看板主页面（协调层，1665行）
│       │   └── settings_window.py   # 设置面板（overlay可拖拽）
│       ├── components/
│       │   ├── kanban_board.py      # 9列看板
│       │   ├── kanban_column.py     # 看板列（拖放支持）
│       │   ├── task_card.py         # 任务卡片
│       │   ├── ai_chat.py           # AI对话面板
│       │   ├── chat_bubble.py       # 聊天气泡（用户/AI/错误/提示）
│       │   ├── chat_input.py        # 输入框（发送/中止按钮）
│       │   ├── ai_suggestion.py     # 机队状态栏
│       │   ├── side_panel.py        # 任务详情侧边栏
│       │   ├── bottom_status_bar.py # 底部任务状态栏
│       │   ├── command_bar.py       # Ctrl+K 命令面板
│       │   ├── md_renderer.py       # Markdown→Flet TextSpan
│       │   ├── create_task_dialog.py # 新建任务弹窗（GhostTextField）
│       │   └── modal_dialog.py      # 通用模态弹窗
│       ├── controllers/
│       │   └── board_controller.py  # 看板控制器（UI↔Core桥梁）
│       ├── dialogs/                 # 6个独立弹窗模块
│       │   ├── edit_dialog.py       # 编辑任务（含状态锁定逻辑）
│       │   ├── schedule_dialog.py   # 排程（含员工自动补全）
│       │   ├── submit_dialog.py     # 提交验收
│       │   ├── priority_dialog.py   # 优先级选择
│       │   ├── filter_dialog.py     # 筛选
│       │   └── block_dialog.py      # 阻塞
│       ├── services/                # 7个服务模块
│       │   ├── ai_commands.py       # AI命令处理（7个工具+右键AI）
│       │   ├── board_renderer.py    # 看板渲染+幽灵卡注入
│       │   ├── proposal_handler.py  # 幽灵卡接受/拒绝
│       │   ├── cancel_coordinator.py # 取消流程幽灵清除
│       │   ├── context_menu_builder.py # 9列右键菜单
│       │   ├── dialog_builder.py    # 弹窗header/footer/按钮+表单字段工厂
│       │   ├── ai_command_runner.py # AI命令guard/setup/cancel
│       │   ├── task_registry.py     # 线程安全任务注册表
│       │   ├── agent_service.py     # UI↔Agent桥接
│       │   └── ai_completion.py     # 内联AI补全服务
│       └── widgets/
│           ├── toast.py             # Toast通知
│           ├── context_menu.py      # 右键菜单（overlay定位）
│           ├── ghost_text.py        # AI内联幽灵文本（含字段过滤器）
│           ├── ai_ghost_card.py     # AI幽灵任务卡片
│           ├── ai_suggestion_bar.py # AI建议条
│           ├── overlay_dimmer.py    # 全屏变暗遮罩（原生布局）
│           ├── badge.py             # 徽标组件
│           └── notification_bubble.py # 通知气泡
│
├── scripts/
│   ├── build_kb.py                  # 知识库构建
│   ├── extract_worker.py            # PDF 提取子进程
│   ├── gen_demo_json.py             # 演示数据生成
│   ├── agent_demo.py                # Agent 终端测试
│   └── legacy_demo_data.py          # 遗留演示数据（已废弃）
│
├── tests/
│   ├── conftest.py
│   ├── test_core/                   # 核心业务测试
│   ├── test_knowledge/              # 知识库测试
│   ├── test_agent/                  # Agent 测试
│   └── test_ui/                     # UI 测试（待补充）
│
├── docs/                            # 开发文档
│   ├── DEV_GUIDE.md                 # 开发指南（加功能/维护须知）
│   ├── REFACTOR_SUMMARY_20260705.md # 重构总结
│   ├── CODE_QUALITY_REVIEW.md       # 代码质量审查
│   └── REFACTORING_PLAN.md          # 重构计划
│
├── data/
│   ├── board_state.json             # 看板持久化
│   ├── employees.json               # 员工数据
│   ├── logs/                        # 日志（tasksense.log + 轮转）
│   ├── knowledge_base/              # PDF源文件
│   └── vector_store/                # ChromaDB
│
└── sources/                         # 字体（HarmonyOS Sans SC）
```

## 技术栈

| 层 | 技术 | 版本 |
|---|---|---|
| UI | Flet | **0.28.3（锁定）** |
| 嵌入模型 | BGE-m3 (BAAI) | sentence-transformers |
| 向量存储 | ChromaDB | Rust backend |
| LLM | OpenAI-compatible API | DeepSeek / Anthropic |
| PDF 提取 | pypdf | 6.x |
| 测试 | pytest | 311 passed |
| Python | ≥ 3.12 | |

## 快速开始

```bash
# 1. 虚拟环境
python -m venv .venv
.venv\Scripts\activate    # Windows

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置 LLM API（编辑 settings.json）
{
  "llm": {
    "provider": "anthropic",
    "model": "claude-sonnet-4-6",
    "api_key": "sk-your-key-here",
    "base_url": "https://api.anthropic.com"
  }
}

# 4. 构建知识库（首次运行）
python scripts/build_kb.py extract
python scripts/build_kb.py embed

# 5. 启动
python main.py

# 6. 测试
pytest tests/ -v
```

## 代码质量

| 指标 | 数值 |
|------|------|
| board_page 行数 | 1665（从3538重构-53%） |
| 独立模块 | 17个 |
| 测试 | 311/311 passed |
| 评级 | 架构A- 代码质量A- 可维护性A- |

## 维护要点

- **加新弹窗**：`app/ui/dialogs/xxx.py` → board_page一行import
- **加新右键动作**：`_init_action_handlers` 注册1行 + `_act_*` 3行
- **Flet 0.28.3 不可升级**（API不兼容）
- **取消流程**最易出问题——9条路径，主线程更新UI/后台线程silent return
- 详见 `docs/DEV_GUIDE.md`

## 命令参考

| 命令 | 说明 |
|---|---|
| `python main.py` | 启动应用 |
| `python scripts/build_kb.py extract` | PDF→文本 |
| `python scripts/build_kb.py embed --force` | 嵌入→ChromaDB |
| `python scripts/gen_demo_json.py` | 生成演示数据 |
| `pytest tests/ -v` | 全部测试 (311) |
| `pytest tests/ -q` | 快速摘要 |
