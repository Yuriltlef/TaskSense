# 员工工作台页面 (EmployeeWorkbench)

## 概述

员工工作台是一线维修人员的个人操作页面，负责两个核心动作：

```
就绪(Ready) ──[接单]──▶ 执行中(In Progress) ──[提交验收]──▶ 验收中(Inspection)
```

通过 OverlayDimmer 以模态遮罩层方式打开，700×740 固定面板居中显示。

## 入口

- **标题栏**：点击 👤 用户图标（`PERSON_OUTLINE`），调用 `board_page._open_employee_page()`
- **文件**：`app/ui/app.py` 第 255 行，`app/ui/pages/board_page.py` 第 675 行

## 身份系统

### 数据来源

`app/core/services/employee_service.py` 加载 `data/employees.json`（20 人，18 人可用）。

### 会话级身份

在 `app/core/state.py` 中新增两个字段：

```python
self.current_employee_id: str = ""    # 如 "ZH001"
self.current_employee_name: str = ""  # 如 "张工"
```

会话级别有效，不写入 `to_dict()` / `load_from_dict()`（自动不持久化）。

## 页面结构

### 整体布局（`_build`）

```
┌────────────────── 700px ──────────────────┐
│ Header  │ 👤 员工工作台              [✕]  │
├───────────────────────────────────────────┤
│ Body                                       │
│  ┌─ 状态 A：身份选择 ──────────────────┐  │
│  │  🪪 图标                              │  │
│  │  提示文字                              │  │
│  │  [搜索框 ──────────────────── 580px]  │  │
│  │  ┌─ 员工列表 ─────────────────────┐  │  │
│  │  │ 张工  ZH001  mechanical  ...   │  │  │
│  │  │ 李工  ZH002  avionics  ...     │  │  │
│  │  │ ...                            │  │  │
│  │  └────────────────────────────────┘  │  │
│  │  [ ✓ 确认身份 ]                       │  │
│  └──────────────────────────────────────┘  │
│                                             │
│  ┌─ 状态 B：任务列表 ──────────────────┐  │
│  │  张工 (ZH001) · mechanical · ... 切换 │  │
│  │  ─────────────────────────────────── │  │
│  │  📋 待接单            [2]             │  │
│  │  ┌────────────────────────────────┐  │  │
│  │  │ ▌ 任务卡片...        [接单]    │  │  │
│  │  └────────────────────────────────┘  │  │
│  │  🔧 进行中            [1]             │  │
│  │  ┌────────────────────────────────┐  │  │
│  │  │ ▌ 任务卡片...     [提交验收]   │  │  │
│  │  └────────────────────────────────┘  │  │
│  │           待接单 2 · 进行中 1         │  │
│  └──────────────────────────────────────┘  │
├───────────────────────────────────────────┤
│ Footer                               [关闭]│
└───────────────────────────────────────────┘
```

### 关键尺寸

| 元素 | 值 |
|------|-----|
| 面板 | 700×740 |
| 搜索框/列表宽度 | 580px |
| body 内边距 | s(16) ≈ 19px 水平, s(12) ≈ 14px 垂直 |

## 双状态设计

### 状态 A：选择身份

当 `state.current_employee_id` 为空时显示。

**组件**：
- 搜索框（`TextField`）：实时过滤员工列表，支持按姓名、ID、工种搜索
- 员工列表（`Column` 内嵌 `Container` 列表）：可滚动，点击选中高亮
- 确认按钮（`ElevatedButton`）：选中员工后点击确认

**交互**：
1. 搜索框输入 → `_on_emp_search` → 实时过滤 `_populate_emp_list`
2. 点击列表项 → `_on_emp_select` → 设置 `cls._selected_emp_id`，重新渲染高亮
3. 点击"确认身份" → `_on_confirm_identity` → 写入 `state.current_employee_id/name` → 切换到状态 B

**关键方法**：

| 方法 | 作用 |
|------|------|
| `_rebuild_body_state_a()` | 构建身份选择界面 |
| `_populate_emp_list(results_list, employees, ff, filter_text)` | 填充/刷新员工列表，支持搜索过滤 |
| `_on_emp_select(eid, ...)` | 选中员工，高亮当前项 |
| `_on_emp_search(e, ...)` | 搜索过滤回调 |
| `_on_confirm_identity()` | 确认身份，切换到状态 B |

### 状态 B：任务列表

当 `state.current_employee_id` 非空时显示。

**数据获取**：

```python
# 待接单
ready_tasks = [t for t in state.get_tasks_by_column("ready")
               if t.employee_id == state.current_employee_id]

# 进行中
in_progress_tasks = [t for t in state.get_tasks_by_column("in_progress")
                     if t.employee_id == state.current_employee_id]
```

**组件**：
- 身份信息行：姓名、ID、工种、机型认证、班次 + "切换身份"按钮
- 待接单区域：section header + 任务卡片列表 + 空状态占位
- 进行中区域：section header + 任务卡片列表 + 空状态占位
- 底部统计：待接单 N 项 · 进行中 M 项

**任务卡片**（`_make_task_card`）：

```
┌─────────────────────────────────────────────────┐
│ ▌ WO-xxx  ·  任务标题...              [接单]    │
│    B-5823 · ATA 32-41-03                        │
└─────────────────────────────────────────────────┘
```

- 左色带：优先级颜色（AOG=红, CatA=橙, CatB=黄, CatC=蓝, CatD=灰）
- 标题截断 46 字符
- 信息行：工卡号 + 飞机注册号 + ATA 章节
- Ready 列任务显示绿色"接单"按钮
- In Progress 列任务显示蓝色"提交验收"按钮 + checklist 进度
- 悬停高亮（`on_hover` → `_on_card_hover`）

**空状态**：无任务时显示斜体灰色文字"暂无待接单任务"/"暂无进行中的任务"

**关键方法**：

| 方法 | 作用 |
|------|------|
| `_rebuild_body_state_b()` | 构建任务列表界面 |
| `_build_task_section(title, tasks, section_type, empty_text)` | 构建任务区域（header + 卡片列表） |
| `_make_task_card(task, section_type)` | 构建单个任务卡片 |
| `_on_card_hover(e)` | 卡片悬停高亮 |
| `_on_switch_identity()` | 清除身份，切回状态 A |

## 接单流程（Ready → In Progress）

### 触发

任务卡片上的"接单"按钮 → `_act_accept(task)`

### 校验链（逐条检查，任一失败即 Toast 报错并中断）

| 步骤 | 校验内容 | 失败提示 |
|------|---------|---------|
| 1 | 任务存在 | "任务不存在" |
| 2 | 员工可用 (`employee_service.validate`) | "当前员工不可用" |
| 3 | 任务仍在 Ready 列 | "任务状态已变化，请刷新" |
| 4 | 任务归属当前员工 (`t.employee_id == state.current_employee_id`) | "该任务未指派给您" |
| 5 | WIP 限制 (`in_progress` 列当前任务数 < 15) | "执行中列已达上限(15)" |

### 确认界面（`_show_confirm_dialog`）

不使用 `AlertDialog`（会被 OverlayDimmer 遮挡），而是**替换 `cls._body.content`** 为确认界面：

```
┌──────────────────────────────┐
│          ❓ 图标              │
│        确认接单               │
│                              │
│  任务: 前起落架转向异响排查    │
│  B-5823 · ATA 32-41-03       │
│                              │
│  确认接单后将开始计时         │
│                              │
│    [取消]    [✓ 确认接单]     │
└──────────────────────────────┘
```

- "取消" → 恢复保存的 `_prev_body` 内容
- "确认接单" → `do_accept`
  - 若 `planned_start` 为空，设为当前时间
  - `task_service.move_task(task.id, "in_progress", changed_by=当前员工姓名)`
  - 调用 `_rebuild_body_state_b()` 刷新列表
  - Toast "已接单，任务进入执行中"
  - 异常时恢复原 body 内容

## 提交验收流程（In Progress → Inspection）

### 触发

任务卡片上的"提交验收"按钮 → `_act_submit(task)`

### 校验

| 步骤 | 校验内容 | 失败提示 |
|------|---------|---------|
| 1 | 任务存在 | "任务不存在" |
| 2 | 任务仍在 In Progress 列 | "任务状态已变化，请刷新" |
| 3 | 任务归属当前员工 | "该任务未指派给您" |
| 4 | checklist 进度（仅警告，不阻断） | "检查清单未完成 (4/8)" |

### 弹窗

复用 `app/ui/dialogs/submit_dialog.py`，传入 `changed_by=state.current_employee_name`：

- 交接班日志（必填）
- 实际工时（选填）
- 确认后：`task_service.move_task(tid, "inspection", changed_by=...)`
- 状态同步自动刷新员工页面（通过 `state.subscribe` 监听器）

## 状态同步

员工页面通过 `state.subscribe()` 注册监听器，在看板状态变更时自动刷新任务列表：

```
move_task → state._notify() → _on_state_changed → _rebuild_body_state_b → page.update
```

关键设计：`_on_state_changed` 检查 `cls._open` 和 `state.current_employee_id`，两个条件都满足才刷新。

## 关联变更（本功能涉及的其他文件）

| 文件 | 改动 |
|------|------|
| `app/core/state.py` | `current_employee_id` / `current_employee_name` 字段 |
| `app/ui/app.py` | 标题栏 PERSON_OUTLINE 按钮绑定 |
| `app/ui/pages/board_page.py` | `_open_employee_page()` 入口方法 |
| `app/ui/services/context_menu_builder.py` | Ready 列保留"开始执行"，In Progress 列删除"提交验收""直接完成" |
| `app/core/services/board_scheduler.py` | 删除 Ready→InProgress 自动流转分支 |
| `app/ui/dialogs/submit_dialog.py` | `changed_by` 参数化（默认 `"user"`） |

## 两条 Ready→InProgress 路径对比

| 路径 | 触发 | 校验 | 确认 |
|------|------|------|------|
| 员工工作台"接单" | 选身份后点按钮 | 归属 + 可用 + WIP | 内联确认 |
| 右键"开始执行" | Ready 列右键菜单 | 无 | 无 |

## 注意事项

1. **Flet 0.28.3 兼容性**：`ElevatedButton` 只能使用 `text`+`icon` 参数，不支持 `content`；`Container.on_click` 在 scrollable Column 内不可靠
2. **确认弹窗**：不能用 `page.dialog`（会被 OverlayDimmer 遮挡），改用替换 body 内容的方式
3. **员工列表字体**：Flet 0.28.3 的 `Dropdown` 菜单项不支持自定义字体，因此改用搜索框+自绘列表
4. **`changed_by`**：员工页面操作时传入员工姓名（如"张工"），便于审计日志追溯
5. **身份不持久化**：关闭应用后需要重新选择员工身份
