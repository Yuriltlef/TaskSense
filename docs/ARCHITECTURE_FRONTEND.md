# TaskSense 前端架构（表现层）

## 架构概览

```
main.py (Flet 入口)
    │
    ▼
app/ui/app.py (UI 应用初始化)
    │
    ├─► 路由注册 → pages/
    │
    ├─► 主题加载 ← app/config/theme.py
    │
    └─► Controller 绑定
         │
         ▼
    controllers/board_controller.py (UI ↔ Core 桥梁)
         │
         ▼
    app/core/services/ (业务逻辑)
```

## 分层结构

```
app/ui/
├── app.py                 # UI 应用工厂
├── controllers/           # 页面控制器（UI 状态 + Core 调用）
│   └── board_controller.py
├── pages/                 # 页面（路由目标）
│   ├── board_page.py      # 看板主页
│   ├── fleet_page.py      # 机队总览
│   └── report_page.py     # 报告页
├── components/            # 可复用业务组件
│   ├── kanban_board.py    # 看板主体
│   ├── kanban_column.py   # 看板列
│   ├── task_card.py       # 任务卡片
│   ├── side_panel.py      # 右侧详情面板
│   ├── command_bar.py     # Cmd+K 命令面板
│   ├── ai_suggestion.py   # AI 建议区域
│   ├── search_bar.py      # 搜索栏
│   ├── notification.py    # 通知组件
│   └── fleet_status.py    # 机队状态顶栏
└── widgets/               # 基础 UI 控件
    ├── badge.py           # 优先级/状态徽章
    ├── ghost_text.py      # AI 幽灵文本输入
    ├── context_menu.py    # 右键菜单
    └── toast.py           # Toast 通知
```

---

## 核心设计模式

### 模式 1：Controller 桥接

UI 组件不直接调用 Core 服务。所有交互通过 `Controller` 中转。

```
用户点击 "移动卡片"
    │
    ▼
task_card.on_drop(column_id)
    │
    ▼
board_controller.move_task(task_id, to_column)
    │                           │
    │                    ① 调用 service
    │                    ② 更新 state
    │                    ③ 返回新 state
    │                           │
    ▼                           ▼
page.update()             board_service.move_task(...)
```

**Controller 职责：**
- 持有 UI 局部状态（如当前展开的卡片、活动过滤器）
- 调用 Core 层 Service 执行业务操作
- 将 Core 层返回的数据转换为 UI 可消费的格式
- 管理 UI 交互状态（loading、error、success）

### 模式 2：组件组合

页面由组件树构成，数据单向向下传递：

```
BoardPage
├── FleetStatusBar          ← fleet_status.py
├── SearchBar               ← search_bar.py
├── KanbanBoard             ← kanban_board.py
│   ├── KanbanColumn × 9    ← kanban_column.py
│   │   └── TaskCard × N    ← task_card.py
│   └── CommandBar          ← command_bar.py (Ctl+K 唤起)
├── SidePanel               ← side_panel.py
│   ├── TaskDetailForm
│   ├── AISuggestion        ← ai_suggestion.py
│   └── KnowledgeRefs
└── NotificationContainer   ← notification.py
```

### 模式 3：事件冒泡

组件通过回调函数向父组件传递事件：

```python
# task_card.py
class TaskCard:
    def __init__(self, task, on_click=None, on_drop=None, on_context_menu=None):
        self.on_click = on_click          # → Column → Board → Controller
        self.on_drop = on_drop            # → 处理拖拽
        self.on_context_menu = on_context_menu  # → 打开右键菜单
```

---

## 组件详细设计

### 1. KanbanBoard（看板主体）

```python
class KanbanBoard:
    """
    水平滚动的列容器。
    
    职责：
    - 渲染 9 个 KanbanColumn
    - 处理列间拖拽
    - 管理列可见性（折叠/展开）
    - 协调列内排序
    
    Props：
    - columns: list[ColumnData]     # 列配置
    - tasks: dict[col_id, list[Task]] # 按列分组的任务
    - filters: FilterState          # 当前筛选条件
    - swimlane_by: Optional[str]    # Swimlane 分组维度
    
    Events：
    - on_move_task(task_id, from_col, to_col, index)
    - on_card_click(task_id)
    """
```

**实现要点：**
- 使用 Flet `Row` + `ListView` 实现水平滚动
- 每列独立 `DragTarget`，卡片为 `Draggable`
- Swimlane 模式：在同一列内按分组维度拆分子区域
- 列头显示卡片计数 + WIP 限制进度条

### 2. KanbanColumn（看板列）

```python
class KanbanColumn:
    """
    单列看板列。
    
    职责：
    - 渲染列头（标题、计数、菜单按钮）
    - 渲染列内卡片列表
    - 接收拖放（DragTarget）
    - WIP 限制可视化
    
    Props：
    - column: ColumnData           # 列元数据
    - tasks: list[Task]            # 该列任务
    - wip_limit: Optional[int]     # WIP 限制
    - collapsed: bool              # 是否折叠
    
    Events：
    - on_drop(task_id, index)
    - on_card_click(task_id)
    - on_column_menu(action)       # 列头菜单
    """
```

**列头样式：**
```
┌─ In Progress (5/10) ──── [▼][···] ─┐  ← WIP 正常
┌─ In Progress (12/10) ─── [▼][⚠]  ─┐  ← WIP 超限，红色高亮
```

### 3. TaskCard（任务卡片）

```python
class TaskCard:
    """
    看板卡片 — 系统中最核心的 UI 组件。
    
    职责：
    - 三级渐进信息展示（L1 默认 / L2 悬浮 / L3 侧面板）
    - 拖拽源（Draggable）
    - 右键菜单触发
    
    Props：
    - task: Task
    - expanded_level: int = 1      # 当前展开级别
    
    Events：
    - on_click(task_id)             # → 打开侧面板 (L3)
    - on_hover(task_id)             # → 显示悬浮预览 (L2)
    - on_drag_start / on_drag_end
    - on_context_menu(task_id, pos)
    """
```

**卡片渲染逻辑：**

```python
def build_card(self, level: int) -> ft.Control:
    if level == 1:
        return self._build_compact_card()   # 标题 + 优先级 + ATA + 尾号
    elif level == 2:
        return self._build_preview_card()   # + 摘要 + 子任务数 + 关联文档
    elif level == 3:
        return None  # 由 SidePanel 接管
```

**L1 紧凑卡片布局：**
```
┌──────────────────────────────────┐
│ 🔴 AOG  ██ ATA 32-41-03        │  ← 左侧色条 (4px) + ATA 标签
│                                  │
│ 前起落架转向异响排查             │  ← 标题 (最多2行，溢出省略)
│                                  │
│ B-5823 · 737-800 · Zone 710    │  ← 飞机注册号 · 机型 · 区域
│                                  │
│ 👤张工  ⏱4.5h  📅06-27 14:00  │  ← 技师 · 工时 · 截止
│                                  │
│ 🏷排故  ⚠零件待确认  💬3  📎5  │  ← 类型 · 警告 · 评论 · 附件
└──────────────────────────────────┘
```

### 4. SidePanel（右侧详情面板）

```python
class SidePanel:
    """
    点击卡片后从右侧滑出的详情面板。
    
    职责：
    - 任务完整信息展示
    - 内嵌 AI 建议区域
    - RAG 检索结果展示
    - 操作历史时间线
    - 编辑模式切换
    
    结构：
    ┌─ SidePanel ─────────────────────────┐
    │ [← 关闭] [编辑] [···]                │  ← 工具栏
    │ ──────────────────────────────────── │
    │ 📋 详情 (Tab)                         │
    │   ├─ 标题、ATA、优先级、状态          │
    │   ├─ 飞机信息、区域、工时             │
    │   ├─ 检查清单                         │
    │   └─ 评论                             │
    │ ──────────────────────────────────── │
    │ 🤖 AI 建议 (Tab)                      │
    │   ├─ 操作建议                         │
    │   ├─ 警告/告警                        │
    │   ├─ 关联知识库                       │
    │   └─ 预测                             │
    │ ──────────────────────────────────── │
    │ 📜 历史 (Tab)                         │
    │   └─ 时间线                           │
    └──────────────────────────────────────┘
    
    Props：
    - task_id: Optional[str]       # None 时关闭
    - active_tab: str = "detail"
    
    Events：
    - on_close()
    - on_edit(task_id, field, value)
    - on_accept_suggestion(suggestion_id)
    """
```

**动画：** 使用 Flet `AnimatedSwitcher` 或手动 `animate` 实现从右滑入（200ms ease-out）。

### 5. CommandBar（命令面板）

```python
class CommandBar:
    """
    Cmd+K 唤起的命令面板。
    
    职责：
    - 全局搜索（任务、知识库、命令）
    - 快速操作入口
    - 自然语言查询
    
    模式：
    ┌─ Cmd+K ────────────────────────────┐
    │ 🔍 搜索、跳转、或输入操作...         │  ← TextField 自动聚焦
    │                                      │
    │ ── 操作 ─────────────────────────── │
    │ > 创建排故任务                       │
    │ > 生成今日班次报告                    │
    │ > 检查 AD 合规状态                   │
    │                                      │
    │ ── 导航 ─────────────────────────── │
    │ > 跳转到 ATA 32 看板                  │
    │ > 查看机队状态总览                    │
    │                                      │
    │ ── 任务 ─────────────────────────── │
    │ > B-5823 起落架排故                  │
    │ > A320neo 右发滑油检查               │
    └──────────────────────────────────────┘
    
    实现：
    - Flet AlertDialog（全屏遮罩）
    - 输入防抖 200ms 触发搜索
    - ↑↓ 导航结果，Enter 执行，Esc 关闭
    - 混合搜索：精确匹配 > 语义匹配 > 命令匹配
    """
```

### 6. AISuggestion（AI 建议区域）

```python
class AISuggestion:
    """
    侧面板中的 AI 建议区域。
    
    职责：
    - 展示 Agent 生成的操作建议
    - 展示 Agent 生成的警告
    - 展示 RAG 检索到的相关知识
    - 展示预测信息
    
    子组件：
    ┌─ AI 建议 ─────────────────────────┐
    │                                     │
    │ 💡 操作建议                         │
    │ ├─ SuggestionCard（可操作）         │
    │ │  📋 生成标准排故工卡    [执行]    │
    │ ├─ SuggestionCard（可操作）         │
    │ │  🔍 查看历史相似故障    [查看]    │
    │ └─ SuggestionCard（可导航）         │
    │    📖 打开 AMM 32-41-03    [打开]  │
    │                                     │
    │ ⚠ 警告                             │
    │ ├─ AlertCard（红色）               │
    │ │  重复故障（30天内）              │
    │ ├─ AlertCard（黄色）               │
    │ │  零件库存不足                     │
    │ └─ AlertCard（橙色）               │
    │    AD 2024-08-15 适用此组件        │
    │                                     │
    │ 📖 相关知识                         │
    │ ├─ KnowledgeRefCard               │
    │ │  AMM 32-41-03 Page 101  94%    │
    │ └─ KnowledgeRefCard               │
    │    历史工单 #WO-2406-0321  91%    │
    └─────────────────────────────────────┘
    """
```

### 7. GhostTextField（幽灵文本输入）

```python
class GhostTextField:
    """
    支持 AI 建议的文本输入控件。
    
    行为：
    1. 用户输入 → 停止 400ms → 触发 AI 推理
    2. AI 返回建议 → 以半透明文本显示在光标后
    3. Tab → 接受建议
    4. Esc → 拒绝建议
    5. 继续输入 → 自动清除建议
    6. 回车 → 使用当前值（不含建议）
    
    实现：
    ┌─ GhostTextField ────────────────────┐
    │ 起落架异响排查│前轮转向作动筒可能故障 │
    │ ← 用户输入    │← AI 建议 (opacity 0.4)│
    └──────────────────────────────────────┘
    
    Props：
    - value: str
    - ghost_text: Optional[str]    # AI 生成的建议
    - loading: bool               # 是否正在等待 AI 响应
    - on_change(value)            # 值变更回调
    - on_accept_ghost(value)      # 接受建议回调
    """
```

---

## 页面路由

```python
# app/ui/app.py

ROUTES = {
    "/": BoardPage,           # 看板主页
    "/fleet": FleetPage,      # 机队总览
    "/reports": ReportPage,   # 报告页
}
```

使用 Flet 的 `page.go()` 或视图切换实现路由，避免整页刷新。

---

## 状态管理：Controller 模式

```python
class BoardController:
    """
    看板页面的控制器。
    
    职责：
    - 持有 UI 层状态（筛选器、展开卡片、加载状态）
    - 调用 Core 层 Service
    - 将 Core 数据转换为 UI Props
    
    状态：
    - tasks: dict[str, list[Task]]
    - columns: list[ColumnData]
    - filters: FilterState
    - selected_task_id: Optional[str]
    - active_swimlane: Optional[str]
    - loading: set[str]                 # 正在加载的操作
    - errors: list[ErrorInfo]
    
    核心方法：
    - load_board()
    - move_task(task_id, to_col, index)
    - filter_tasks(filters)
    - search_tasks(query)
    - get_ai_suggestions(task_id)
    - execute_command(command)
    """
```

---

## UI 组件通信约定

```python
# ✅ 正确：通过 Controller 回调
class TaskCard:
    def __init__(self, on_move_task: Callable):
        self.on_move_task = on_move_task

    def _handle_drop(self, e):
        self.on_move_task(self.task.id, e.target_column, e.index)

# ❌ 错误：UI 组件直接调用 Service
class TaskCard:
    def _handle_drop(self, e):
        board_service.move_task(...)  # 不允许！
```

---

## 主题与样式

```python
# 从 app/config/theme.py 加载
class AppTheme:
    """暗色航空仪表盘主题"""
    
    COLORS = {
        "bg":             "#0D1117",
        "surface":        "#161B22",
        "card":           "#1C2333",
        "card_hover":     "#21283D",
        "border":         "#30363D",
        "text_primary":   "#E6EDF3",
        "text_secondary": "#8B949E",
        "text_disabled":  "#484F58",
        
        # 优先级
        "priority_aog":   "#FF4444",
        "priority_cata":  "#FF8C00",
        "priority_catb":  "#FFD700",
        "priority_catc":  "#58A6FF",
        "priority_catd":  "#8B949E",
        
        # 任务类型
        "type_trouble":   "#F78166",
        "type_inspect":   "#7EE787",
        "type_service":   "#79C0FF",
        "type_r_i":       "#D2A8FF",
        "type_test":      "#FFA657",
        
        # 状态
        "success":        "#2E7D32",
        "warning":        "#FFA000",
        "error":          "#C62828",
    }
```

---

## 响应式适配

```python
class ResponsiveLayout:
    """
    根据窗口宽度切换布局模式。
    
    >= 1280px    → 三栏：导航 + 看板 + 侧面板
    1024~1279px  → 两栏：看板 + 侧面板（导航折叠为图标栏）
    768~1023px   → 单栏：看板（侧面板覆盖全屏）
    < 768px      → 单栏：单列滑动模式
    """
    
    @staticmethod
    def get_layout(width: float) -> LayoutMode:
        if width >= 1280:
            return LayoutMode.DESKTOP
        elif width >= 1024:
            return LayoutMode.TABLET_LANDSCAPE
        elif width >= 768:
            return LayoutMode.TABLET_PORTRAIT
        else:
            return LayoutMode.MOBILE
```
