# OverlayDimmer — 可复用的全屏变暗遮罩

## 问题背景

Flet 0.28.3 中 `page.dialog` 不工作，所有弹窗/设置面板统一使用 `page.overlay` 方案。但早期实现只有面板本身，缺少全屏变暗的遮罩层，导致弹窗打开时背后内容没有视觉区分。

## 原理

```
page.overlay.append(
    Stack([
        Container(                          ← 变暗层
            width=page.width,
            height=page.height,
            bgcolor=ft.Colors.BLACK,
            opacity=0.65,                   ← 核心：opacity 属性降低不透明度
            on_click=close,                 ← 点击遮罩关闭（可选）
        ),
        panel_content,                      ← 内容面板（置于遮罩上方）
    ])
)
```

关键点：

- **`page.overlay` 中不能使用 `expand=True`**，控件没有父布局来分配空间。必须显式设 `width=page.width, height=page.height`
- **`bgcolor` 带 alpha 通道的 hex 格式（`#00000066`）在 0.28.3 中不渲染**，需用 `Container.opacity` 属性替代
- **Stack 的子控件按顺序叠放**：先变暗层（底层）→ 后面板（顶层）

## 幽灵卡片原理（同款技术）

拖拽时的半透明效果用的也是 `opacity`：

```python
# task_card.py
if ghost:
    self.bgcolor = ft.Colors.TRANSPARENT    # 背景透明
    self.opacity = 0.45                      # 整卡 45% 不透明度
    self.border = ft.border.all(1.5, ...)   # 细描边勾勒轮廓
    self.shadow = None                       # 去投影
```

`Container.opacity` 作用于整个控件及其所有子控件（文字、图标、徽章全部变淡）。

## 组件用法

### 基本：打开一个带遮罩的弹窗

```python
from app.ui.widgets.overlay_dimmer import OverlayDimmer

# 一行打开
dimmer = OverlayDimmer.open(page, my_panel)

# 手动控制
dimmer = OverlayDimmer(page, my_panel)
dimmer.show()
dimmer.close()
```

### 点击遮罩关闭（默认行为）

```python
dimmer = OverlayDimmer.open(page, my_panel)
# 点击变暗区域 → 自动关闭
```

### 禁止点击遮罩关闭

```python
dimmer = OverlayDimmer.open(
    page, my_panel, close_on_dimmer_click=False)
```

### 自定义变暗程度

```python
dimmer = OverlayDimmer.open(
    page, my_panel, dim_opacity=0.7)  # 0.0=全透明, 1.0=全黑
```

### 自定义遮罩点击回调

```python
def on_dim_click():
    if has_unsaved_changes:
        show_confirm_dialog()
    else:
        dimmer.close()

dimmer = OverlayDimmer.open(
    page, my_panel, on_dimmer_click=on_dim_click)
```

## 接入现有弹窗

### 模式 A：用 OverlayDimmer 替代直接 append（推荐）

把原来：

```python
page.overlay.append(my_panel)
page.update()
```

改为：

```python
self._dimmer = OverlayDimmer.open(page, my_panel)
```

关闭时：

```python
# 原来
page.overlay.remove(my_panel)

# 改为
self._dimmer.close()
```

完整示例——对接现有的单例模式弹窗：

```python
from app.ui.widgets.overlay_dimmer import OverlayDimmer

class MyDialog:
    _dimmer: OverlayDimmer | None = None
    _page: ft.Page | None = None
    _open = False

    @classmethod
    def open(cls, page: ft.Page):
        if cls._open:
            return
        cls._page = page
        cls._open = True

        # 构建面板内容（和之前一样）
        panel = cls._build_panel()

        # 用 OverlayDimmer 包裹
        cls._dimmer = OverlayDimmer.open(page, panel, dim_opacity=0.65)

    @classmethod
    def close(cls):
        if not cls._open:
            return
        cls._open = False
        if cls._dimmer:
            cls._dimmer.close()
            cls._dimmer = None
```

### 模式 B：面板需要拖拽

如果弹窗面板需要可拖拽（如设置面板），**只在标题栏内**放置 GestureDetector，面板整体定位不变。然后传给 OverlayDimmer：

```python
# 标题栏（内嵌拖拽，GestureDetector 只包标题不包整个面板）
title_bar = ft.Container(
    content=ft.GestureDetector(
        content=ft.Row([...]),
        mouse_cursor=ft.MouseCursor.MOVE,
        on_pan_start=on_bar_start,
        on_pan_update=on_bar_update,
    ),
    height=37,
)

# 面板（不包 GestureDetector）
panel = ft.Container(
    content=ft.Column([title_bar, body, footer]),
    left=cx, top=cy,
)

# 包裹进遮罩
cls._dimmer = OverlayDimmer.open(page, panel, dim_opacity=0.65)
```

注意：GestureDetector 不要包裹整个面板——否则点击表单、滚动条都会触发拖拽。

### 模式 C：多个弹窗嵌套

OverlayDimmer 内部追踪 `_open` 状态，重复 `show()` 不会创建多个遮罩。但如果需要多个遮罩叠加（如确认框叠在设置面板上），创建两个独立的 `OverlayDimmer` 实例即可。

## API 参考

### 构造函数

```python
OverlayDimmer(
    page: ft.Page,
    content: ft.Control,
    *,
    dim_opacity: float = 0.4,          # 变暗程度 0.0~1.0
    on_dimmer_click: Callable = None,   # 点击遮罩回调
    close_on_dimmer_click: bool = True, # 点击遮罩是否自动关闭
)
```

### 方法

| 方法 | 说明 |
|------|------|
| `OverlayDimmer.open(page, content, **kw)` | 类方法，创建并立即打开 |
| `show()` | 显示遮罩 |
| `close()` | 关闭遮罩 |
| `is_open` | 属性，是否已打开 |

## 相关文件

- `app/ui/widgets/overlay_dimmer.py` — 组件实现
- `app/ui/pages/settings_window.py` — 使用示例（设置面板，拖拽仅标题栏）
- `app/ui/components/create_task_dialog.py` — 使用示例（新建任务弹窗，点击遮罩关闭）
- `app/ui/components/task_card.py` — `ghost=True` 模式，同款 opacity 技术
