# 统一按钮样式规范

## 设计原则

- 字体：全局统一 `HarmonyOS Sans SC`（`theme.font_family`）
- 圆角：`6px`（`RoundedRectangleBorder(radius=6)`）
- 内边距：`left=20, top=8, right=20, bottom=8`
- 字号：`13px`
- 描边：`1px`
- 交互：hover 时变亮（`overlay_color`），点击时加深（`elevation` / `overlay_color`）

## 五种按钮样式

### 主要操作（蓝色）

用于：保存、创建、确认等正向操作。

```python
ft.OutlinedButton("保存",
    style=ft.ButtonStyle(
        shape=ft.RoundedRectangleBorder(radius=6),
        padding=ft.padding.only(left=20, top=8, right=20, bottom=8),
        text_style=ft.TextStyle(size=13, font_family=theme.font_family),
        side=ft.BorderSide(1, theme.info),    # 蓝色描边
        color=theme.info,                      # 蓝色文字
    ),
)
```

### 次要操作（灰色/白色）

用于：取消、关闭等负向操作。

```python
ft.OutlinedButton("取消",
    style=ft.ButtonStyle(
        shape=ft.RoundedRectangleBorder(radius=6),
        padding=ft.padding.only(left=20, top=8, right=20, bottom=8),
        text_style=ft.TextStyle(size=13, font_family=theme.font_family),
        side=ft.BorderSide(1, theme.border),    # 灰色描边
        color=theme.text_primary,                # 白色/亮字
    ),
)
```

### 警告操作（黄色/橙色）

用于：删除前提示、危险操作警告。

```python
ft.OutlinedButton("删除",
    style=ft.ButtonStyle(
        shape=ft.RoundedRectangleBorder(radius=6),
        padding=ft.padding.only(left=20, top=8, right=20, bottom=8),
        text_style=ft.TextStyle(size=13, font_family=theme.font_family),
        side=ft.BorderSide(1, theme.warning),   # 黄色描边
        color=theme.warning,                     # 黄色文字
    ),
)
```

### 危险操作（红色）

用于：确认删除、不可逆操作。

```python
ft.OutlinedButton("确认删除",
    style=ft.ButtonStyle(
        shape=ft.RoundedRectangleBorder(radius=6),
        padding=ft.padding.only(left=20, top=8, right=20, bottom=8),
        text_style=ft.TextStyle(size=13, font_family=theme.font_family),
        side=ft.BorderSide(1, theme.error),     # 红色描边
        color=theme.error,                       # 红色文字
    ),
)
```

### 实心按钮（蓝色填充）

用于：标题栏"新建任务"等需要突出的操作。

```python
ft.ElevatedButton("新建任务",
    style=ft.ButtonStyle(
        bgcolor="#1565c0",                       # 深蓝填充
        color=ft.Colors.WHITE,                   # 白字
        overlay_color="#1e88e5",                 # hover 微亮
        elevation=1,                             # 轻微投影
        shape=ft.RoundedRectangleBorder(radius=4),
        padding=ft.padding.only(left=12, top=2, right=12, bottom=2),
    ),
)
```

## 主题颜色速查

| 语义 | 变量 | 色值 | 用途 |
|------|------|------|------|
| 信息/主色 | `theme.info` | `#1976d2` | 蓝色，主要操作 |
| 文字主色 | `theme.text_primary` | 白色/亮色 | 次要按钮文字 |
| 文字次色 | `theme.text_secondary` | 灰色 | 辅助说明（不用作按钮） |
| 边框 | `theme.border` | 深灰 | 灰色描边 |
| 警告 | `theme.warning` | 黄色 | 警告操作 |
| 错误 | `theme.error` | 红色 | 危险/删除操作 |
| 卡片背景 | `theme.card` | 深灰 | 卡片/选中项背景 |

## 使用位置

| 位置 | 文件 | 按钮 | 类型 |
|------|------|------|------|
| 标题栏 | `app/ui/app.py:175` | 新建任务 | 实心蓝色 |
| 设置面板 | `app/ui/pages/settings_window.py:153` | 取消 | 灰色次要 |
| 设置面板 | `app/ui/pages/settings_window.py:163` | 保存 | 蓝色主要 |
| 新建任务弹窗 | `app/ui/components/create_task_dialog.py:156` | 取消 | 灰色次要 |
| 新建任务弹窗 | `app/ui/components/create_task_dialog.py:166` | 创建 | 蓝色主要 |

## 新建按钮封装（推荐）

避免重复代码，建议提取公共样式工厂：

```python
# app/ui/widgets/buttons.py
import flet as ft
from app.config.theme import theme

_BASE = dict(
    shape=ft.RoundedRectangleBorder(radius=6),
    padding=ft.padding.only(left=20, top=8, right=20, bottom=8),
    text_style=ft.TextStyle(size=13, font_family=theme.font_family),
)

def primary_btn(label: str, on_click) -> ft.OutlinedButton:
    """蓝色主要按钮"""
    return ft.OutlinedButton(label, on_click=on_click,
        style=ft.ButtonStyle(
            **_BASE,
            side=ft.BorderSide(1, theme.info),
            color=theme.info,
        ))

def secondary_btn(label: str, on_click) -> ft.OutlinedButton:
    """灰色次要按钮"""
    return ft.OutlinedButton(label, on_click=on_click,
        style=ft.ButtonStyle(
            **_BASE,
            side=ft.BorderSide(1, theme.border),
            color=theme.text_primary,
        ))

def danger_btn(label: str, on_click) -> ft.OutlinedButton:
    """红色危险按钮"""
    return ft.OutlinedButton(label, on_click=on_click,
        style=ft.ButtonStyle(
            **_BASE,
            side=ft.BorderSide(1, theme.error),
            color=theme.error,
        ))

def warning_btn(label: str, on_click) -> ft.OutlinedButton:
    """黄色警告按钮"""
    return ft.OutlinedButton(label, on_click=on_click,
        style=ft.ButtonStyle(
            **_BASE,
            side=ft.BorderSide(1, theme.warning),
            color=theme.warning,
        ))
```
