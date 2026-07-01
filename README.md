# TaskSense — 航空维护智能看板系统

基于 Flet 0.28.3 的桌面应用，集成 RAG 知识库 + LLM Agent 的航空维护管理工具。

## 项目架构

```
TaskSense/
├── main.py                          # 入口：预加载 + 启动 Flet app
├── settings.json                    # 运行时配置（LLM/RAG/UI/Agent）
├── pyproject.toml                   # 依赖声明
│
├── app/
│   ├── config/                      # 配置层
│   │   ├── theme.py                 # 暗色主题 + SCALE=1.2 缩放
│   │   ├── settings_manager.py      # settings.json 持久化
│   │   ├── settings.py              # AppSettings dataclass
│   │   └── constants.py             # 航空领域常量（ATA/Priority/TaskType）
│   │
│   ├── core/                        # 核心业务
│   │   ├── state.py                 # 全局状态树（任务/飞机/看板）
│   │   ├── events.py                # EventBus 发布/订阅
│   │   ├── validators.py            # 业务规则校验（WIP/状态转换）
│   │   ├── models/
│   │   │   ├── task.py              # Task/Priority/TaskStatus/TaskType
│   │   │   ├── aircraft.py          # Aircraft/AircraftStatus
│   │   │   └── kanban.py            # BoardState/ColumnConfig/FilterState
│   │   └── services/
│   │       ├── board_service.py     # 看板查询/筛选
│   │       └── task_service.py      # 任务 CRUD
│   │
│   ├── agent/                       # AI Agent
│   │   ├── orchestrator.py          # 工具调用编排器（LLM↔Tool 循环）
│   │   ├── conversation.py          # 多轮对话会话管理
│   │   ├── llm_client.py            # OpenAI-compatible LLM 客户端
│   │   ├── preload.py               # 启动预加载（嵌入模型+KB 预热）
│   │   ├── prompts/                 # 提示词文件（Markdown）
│   │   │   ├── system.md            # Agent 身份/能力/回复风格
│   │   │   ├── tool_use.md          # 工具调用格式/可用工具
│   │   │   ├── strict_mode.md       # 严格模式（仅 KB，详细引用）
│   │   │   └── normal_mode.md       # 普通模式（KB + 在线综合）
│   │   └── tools/
│   │       ├── search_tools.py      # RAG 检索工具
│   │       └── board_tools.py       # 看板操作工具
│   │
│   ├── knowledge/                   # RAG 知识库
│   │   ├── pipeline.py              # 知识库流水线（构建/增量/检索）
│   │   ├── chunker.py               # 内容自适应文本分块器
│   │   ├── embedder.py              # BGE-m3 向量化（CUDA/CPU 自适应）
│   │   ├── loader.py                # PDF 加载器（pypdf + 页码追踪）
│   │   ├── store.py                 # ChromaDB 向量存储（多 Collection）
│   │   └── retriever.py             # 混合检索器（语义 + BM25 + RRF）
│   │
│   └── ui/                          # Flet 桌面 UI
│       ├── app.py                   # 主窗口（标题栏/布局/窗口操作）
│       ├── pages/
│       │   ├── board_page.py        # 看板主页面
│       │   └── settings_window.py   # 设置面板（overlay 可拖拽）
│       ├── components/
│       │   ├── kanban_board.py      # 9 列看板
│       │   ├── kanban_column.py     # 看板列
│       │   ├── task_card.py         # 任务卡片
│       │   ├── ai_chat.py           # AI 对话面板
│       │   ├── chat_bubble.py       # 聊天气泡
│       │   ├── chat_input.py        # 输入框（发送/中止按钮）
│       │   ├── ai_suggestion.py     # 机队状态栏
│       │   ├── side_panel.py        # 任务详情侧边栏
│       │   ├── command_bar.py       # Ctrl+K 命令面板
│       │   ├── md_renderer.py       # Markdown → Flet TextSpan
│       │   ├── create_task_dialog.py # 新建任务弹窗
│       │   ├── global_input.py      # 全局输入
│       │   └── ai_sidebar.py        # AI 侧边栏
│       ├── services/
│       │   └── agent_service.py     # UI↔Agent 桥接层
│       └── widgets/
│           ├── toast.py             # Toast 通知
│           ├── context_menu.py      # 右键菜单
│           ├── badge.py             # 徽标组件
│           └── ghost_text.py        # 占位文本
│
├── scripts/
│   ├── build_kb.py                  # 知识库构建（PDF 提取 + 嵌入）
│   ├── extract_worker.py            # PDF 提取子进程
│   └── agent_demo.py                # Agent 交互式终端测试
│
├── tests/
│   ├── conftest.py                  # Pytest 配置（slow/needs_kb 标记）
│   ├── test_core/                   # 核心业务测试（237 tests）
│   ├── test_knowledge/              # 知识库测试（74 tests）
│   └── test_agent/                  # Agent 测试（含 kb_queries）
│
├── data/
│   ├── knowledge_base/              # 26 个 PDF 源文件
│   │   └── processed/               # pypdf 提取的 .txt 文件
│   └── vector_store/                # ChromaDB 持久化向量
│
└── sources/                         # 字体文件（HarmonyOS Sans SC）
```

## 技术栈

| 层 | 技术 | 版本 |
|---|---|---|
| UI | Flet | **0.28.3（锁定，不可升级）** |
| 嵌入模型 | BGE-m3 (BAAI) | sentence-transformers 4.1.0 |
| 向量存储 | ChromaDB | 1.5.9 (Rust backend) |
| LLM | OpenAI-compatible API | DeepSeek v4 |
| PDF 提取 | pypdf | 6.14.2 |
| 测试 | pytest | 9.1.1 |
| Python | ≥ 3.12 | |

## 快速开始

```bash
# 1. 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate    # Windows

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置 LLM API（编辑 settings.json）
{
  "llm": {
    "provider": "openai",
    "model": "deepseek-v4-flash",
    "api_key": "sk-xxx",
    "base_url": "https://api.deepseek.com"
  }
}

# 4. 构建知识库（需要 GPU 显存 ≥ 4GB）
python scripts/build_kb.py extract    # Phase 1: PDF → 文本
python scripts/build_kb.py embed       # Phase 2: 嵌入 → ChromaDB
# 或一步完成：
python scripts/build_kb.py build --force --cleanup

# 5. 启动应用
python main.py

# 6. 运行测试
pytest tests/ -v
```

## 关键技术细节

### Flet 0.28.3 API 规则

```python
# ✓ 小写 helper 模块
ft.padding.only(left=12, top=8)
ft.padding.all(12)
ft.border.only(bottom=ft.BorderSide(1, color))
ft.border.all(1, color)
ft.alignment.center

# ✓ 大写类名
ft.Colors.WHITE, ft.Colors.TRANSPARENT
ft.MainAxisAlignment.START, ft.FontWeight.W_600
ft.Animation(200, "easeOut")

# ✗ 不存在
ft.Padding.only()      # 必须小写 p
ft.animation            # 模块不存在
ft.colors                # 模块不存在
```

### 标题栏实现（无边框窗口）

```
WindowDragArea(expand=True)            ← 拖拽移动
  └── Container(content=content_row)   ← 标题栏内容
        ├── ✈ | 新建 | 刷新 | 筛选    ← 左侧按钮
        ├── GestureDetector(expand)     ← 双击最大化（仅空白区）
        ├── 搜索框                      ← 居中
        ├── GestureDetector(expand)     ← 双击最大化
        └── AI | 设置 | 用户            ← 右侧按钮

⚠ GestureDetector 不能包裹按钮——会拦截点击事件
⚠ WindowDragArea.on_double_tap 处理双击
⚠ 窗口按钮（最小/最大/关闭）在 WindowDragArea 外部
```

### page.dialog 不可用 → 统一用 page.overlay

```python
# ✗ page.dialog 在当前版本不工作
page.dialog = ft.AlertDialog(...)

# ✓ 设置/弹窗统一用 page.overlay
overlay = ft.Stack([
    ft.Container(bgcolor="#00000066"),  # 遮罩
    panel,                               # 内容面板
])
page.overlay.append(overlay)
# 关闭: page.overlay.remove(overlay)
```

### 分块策略（避免 99% 无效块）

```python
# 1. PDF 预处理：修复断行（英文保留空格）
# 2. ATA 检测：行首锚定 + 验证前缀 ∈ ATA_CHAPTERS
# 3. ≥3 个不同 ATA 标签才确认为 ATA 文档
# 4. Token 估算：len(text) * 0.55（CJK 友好）
# 5. 最短过滤：< 100 字符丢弃
# 6. 相邻短节段合并（同 ATA 章节）
```

### ChromaDB metadata 限制

```python
# ✗ metadata 值不能为 None（Rust backend TypeError）
{"chapter": None}  # 报错

# ✓ 清洗 None 值
{k: v for k, v in meta.items() if v is not None}
```

### embedding 模型预加载

```python
# main.py 设置离线模式前检测缓存
_MODEL_SNAPSHOTS = .model_cache/hub/models--BAAI--bge-m3/snapshots/
if _MODEL_SNAPSHOTS.exists():
    os.environ["HF_HUB_OFFLINE"] = "1"   # 断网运行
else:
    # 允许联网下载，输出英文提示
```

### run_task 正确用法

```python
# ✗ 错误：会立即执行返回 coroutine
self.page.run_task(self._process(val, idx))

# ✓ 正确：存 args，传方法引用
self._pending = val
self.page.run_task(self._process)
```

### 控件必须先挂载再操作

```python
# ✗ 控件还没 add 到 page
self._input.focus()

# ✓ 先 page.update()，再操作
page.update()
self._input.focus()
```

## 常见问题

### Windows GBK 编码
Python 脚本加 `# -*- coding: utf-8 -*-`。print 中文用 `sys.stdout` 包装 utf-8。

### ProcessPoolExecutor 不可用
Windows spawn 模式子进程崩溃。用 `subprocess.Popen` + 独立 worker 脚本。

### DeepSeek max_tokens 上限
393216，我们设 10000。

### TextField filled 自动行为
设 `bgcolor` 自动 `filled=True` → hover 高光。需显式 `filled=False` 或接受。

### WebView 不可用
Windows 不支持 `load_html()`。不要装 `flet-webview`（会升级 Flet）。

### 字体路径
`sources/HarmonyOS_Sans_SC_*.ttf`，通过 `page.fonts` 加载。

### Python 路径
构建脚本用项目 venv：`PROJECT/.venv/Scripts/python.exe`

## 命令参考

| 命令 | 说明 |
|---|---|
| `python main.py` | 启动应用 |
| `python scripts/build_kb.py extract` | PDF → 文本 |
| `python scripts/build_kb.py embed --force` | 嵌入 → ChromaDB |
| `python scripts/build_kb.py build --force --cleanup` | 全量重建 + 清理旧 collection |
| `python scripts/agent_demo.py` | Agent 终端交互测试 |
| `pytest tests/ -v` | 全部测试 (311) |
| `pytest tests/ --run-slow` | 含慢测试 |

## 测试

- **311 passed, 10 skipped**（默认）
- `--run-slow` 启用嵌入模型相关慢测试
- `needs_kb` 标记需要已构建知识库
- `test_knowledge/` 全部无模型加载（mock embeddings），< 20s 完成
