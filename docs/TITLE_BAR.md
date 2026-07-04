# 自绘标题栏

最后更新：2026-07-04

## 概述

TaskSense 使用自绘标题栏替代系统原生标题栏，提供统一的深色界面风格和自定义功能按钮。

## 窗口配置

```python
page.window.frameless = False           # 保留原生边框
page.window.title_bar_hidden = True     # 隐藏系统标题栏
page.window.title_bar_buttons_hidden = True  # 隐藏系统窗口按钮
```

## 布局结构

```
┌──────────────────────────────────────────────────────────────────────────┐
│ ✈ [新建] [刷新] [筛选] [AI工具] │  搜索框  │ [AI助手] [设置] [用户]  ─ □ ✕ │
│◄─── left_group ────────────────►│          │◄── right_group ──►          │
│           ◄══ drag_spacer ══►  │          │  ◄══ drag_spacer ══►       │
└──────────────────────────────────────────────────────────────────────────┘
```

### 控件层级

```
ft.Container (height=s(34), bgcolor=theme.surface)
└── ft.Row([...], spacing=0)
    ├── left_group: ft.Row       ← 左侧功能区（✈ 新建 刷新 筛选 AI工具）
    ├── _drag_spacer             ← WindowDragArea(expand) + GestureDetector
    ├── search_box               ← 搜索框
    ├── _drag_spacer             ← WindowDragArea(expand) + GestureDetector
    ├── right_group: ft.Row      ← 右侧功能区（AI助手 设置 用户）
    └── window_btns              ← 最小化 最大化 关闭
```

## 关键设计规则

### 1. GestureDetector 不能包裹按钮

`GestureDetector` 会拦截所有点击事件等待判断单击/双击（~300ms 延迟），导致按钮反应迟钝。

**正确**：`GestureDetector` 只包裹空白 `Container`。
**错误**：`GestureDetector` 包裹包含按钮的 `Row`。

### 2. 按钮在 WindowDragArea 外部

`WindowDragArea` 内部的任何控件都可以拖拽窗口。搜索框和按钮必须在外部，否则：
- 拖拽搜索框文本 = 移动窗口
- 按钮点击被误判为拖拽

### 3. 只拖拽空白区域

`_drag_spacer` = `WindowDragArea` + 空白 `Container(expand=True)`，不包含任何按钮。

### 4. 新增按钮规范

在 `left_group` 或 `right_group` 中追加：

```python
# 添加到左侧
left_group = ft.Row([
    # ... 现有按钮 ...
    icon_btn(ft.Icons.NEW_FEATURE, callback, "新功能"),
], ...)

# 添加到右侧
right_group = ft.Row([
    # ... 现有按钮 ...
    icon_btn(ft.Icons.NEW_FEATURE, callback, "新功能"),
], ...)
```

## 按钮工厂

### 工具按钮 (`icon_btn`)

```python
icon_btn(icon, on_click, tooltip, icon_color=ft.Colors.GREY_400)
# → width=36, height=34, 方形无圆角, overlay_color="#2a2a2a"
# → tooltip 黑底白字, wait_duration=1500
```

### 窗口按钮 (`win_btn`)

```python
win_btn(icon, on_click, tooltip, hover_color=ft.Colors.GREY_800)
# → 同 icon_btn + mouse_cursor=BASIC
# → 关闭按钮 hover_color=ft.Colors.RED_900
```

## AI 工具下拉菜单

- 使用 `page.overlay` + `Stack` 实现
- `dimmer` 覆盖全屏，`on_tap` 关闭菜单
- 菜单打开时按钮高亮（`bgcolor="#22ffffff"`），关闭时恢复透明
- 菜单位置：`left=s(230), top=s(34)`，宽 180px
- 7 个命令：生成大纲/任务/分类/排程/验收/报表/审核

## 窗口操作

| 操作 | 方法 | 实现 |
|------|------|------|
| 拖拽窗口 | `WindowDragArea` | 空白 spacer 区域 |
| 双击最大化 | `GestureDetector.on_double_tap` | 空白 spacer 区域 |
| 外部最大化检测 | `GestureDetector.on_hover` | Win+↑ 等外部操作 |
| 最小化 | `setattr(page.window, 'minimized', True)` | 必须用 setattr |
| 关闭 | `page.window.close()` | 同步方法 |

## 标题栏插入

标题栏通过 `main_container.content.controls.insert(0, self.title_bar)` 插入到应用顶部。

## 相关文件

| 文件 | 说明 |
|------|------|
| `app/ui/app.py` | 标题栏构建 + AI 菜单 + 窗口操作 |
| `app/ui/pages/board_page.py` | 搜索框引用 + 操作回调 |
| `memory/flet-titlebar-techniques.md` | 标题栏技术记忆 |
