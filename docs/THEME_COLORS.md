# TaskSense 主题色参考

> 所有颜色定义在 `app/config/theme.py` 的 `AppTheme` dataclass 中。
> 禁止在业务代码中硬编码十六进制颜色文字——统一使用 `theme.xxx` 引用。

## 背景层级（极暗灰，仅微亮于纯黑）

| 常量 | 色值 | 用途 |
|------|------|------|
| `theme.bg` | `#080808` | 页面根背景 |
| `theme.surface` | `#0e0e0e` | 列/面板/卡片容器背景 |
| `theme.card` | `#141414` | 任务卡片背景 |
| `theme.card_hover` | `#1a1a1a` | 卡片悬停 / 输入框背景 |
| `theme.border` | `#1e1e1e` | 通用边框 |
| `theme.divider` | `#161616` | 分割线 |
| `theme.panel_dark` | `#111111` | 侧栏/底部栏深色面板 |
| `theme.section_bg` | `#0a0a0a` | 侧栏区块背景 |
| `theme.nav_bg` | `#101010` | 设置左侧导航背景 |

## 文字

| 常量 | 色值 | 用途 |
|------|------|------|
| `theme.text_primary` | `#c8c8c8` | 标题/正文 |
| `theme.text_secondary` | `#6a6a6a` | 次级信息/占位符 |
| `theme.text_disabled` | `#404040` | 禁用态文字 |
| `theme.text_content` | `#c0c0c0` | 侧栏/报告等次级内容 |
| `theme.form_text` | `#e0e0e0` | 表单输入框文字 |
| `theme.text_link` | `#5294e2` | 链接色（同 accent） |

## 主色调 & 状态色

| 常量 | 色值 | 用途 |
|------|------|------|
| `theme.accent` | `#5294e2` | 主色调蓝（图标/按钮/搜索框/高亮） |
| `theme.info` | `#1976d2` | 信息/中性强调 |
| `theme.success` | `#388e3c` | 成功/完成 |
| `theme.warning` | `#e6a000` | 警告/运行中 |
| `theme.error` | `#c62828` | 错误/删除/逾期 |

## 优先级色

| 常量 | 色值 | 优先级 |
|------|------|--------|
| `theme.priority_aog` | `#f44747` | AOG 紧急 |
| `theme.priority_cat_a` | `#e88400` | CAT A |
| `theme.priority_cat_b` | `#e0b800` | CAT B |
| `theme.priority_cat_c` | `#5294e2` | CAT C |
| `theme.priority_cat_d` | `#808080` | CAT D |

## 任务类型色

| 常量 | 色值 | 类型 |
|------|------|------|
| `theme.type_troubleshoot` | `#e87b62` | 排故 |
| `theme.type_inspection` | `#73c990` | 检查 |
| `theme.type_servicing` | `#6db8e8` | 勤务 |
| `theme.type_removal_install` | `#c498e8` | 拆装 |
| `theme.type_test` | `#e8a050` | 测试 |
| `theme.type_repair` | `#4ec9d4` | 修理 |

## 阴影

| 常量 | 色值 | 用途 |
|------|------|------|
| `theme.card_shadow_color` | `#00000030` | 卡片正常阴影 |
| `theme.card_hover_shadow_color` | `#00000050` | 卡片悬停阴影 |
| `theme.menu_shadow_color` | `#00000080` | 右键菜单阴影 |
| `theme.dialog_shadow` | `#000000aa` | 弹窗阴影 |
| `theme.notification_shadow` | `#00000066` | 通知/Toast 阴影 |

## 交互

| 常量 | 色值 | 用途 |
|------|------|------|
| `theme.highlight_border_width` | `2` | 高亮描边宽度（px） |
| `theme.border_active` | `#2a2a2a` | 输入框/搜索框激活边框 |
| `theme.tooltip_bg` | `#202020` | 工具提示背景 |
| `theme.ai_icon` | `#c498e8` | AI 助手图标紫色 |

## 使用方式

```python
from app.config.theme import theme, s, SCALE

# 颜色引用
ft.Container(bgcolor=theme.surface, border=ft.border.all(1, theme.border))
ft.Text("标题", color=theme.text_primary)
ft.Icon(ft.Icons.SETTINGS, color=theme.accent)

# 尺寸缩放（适配高 PPI）
ft.Container(width=s(280), height=s(120))

# 优先级/类型动态色
color = theme.priority_color(task.priority.value)
color = theme.task_type_color(task.task_type.value)
```

## 残留硬编码（合理保留）

以下模块级常量已在各自文件顶部提取，无需移到主题：

| 文件 | 常量 | 说明 |
|------|------|------|
| `chat_bubble.py` | `USER_BG`, `ERROR_BG`, `ERROR_BORDER_*` 等 | 聊天气泡专用色 |
| `bottom_status_bar.py` | `HOVER_BG`, `CANCEL_BG`, `CANCEL_HOVER` | 状态栏专用色 |
| `notification_bubble.py` | 状态 → (color, icon, bg) 字典 | 通知气泡专用色 |
| `md_renderer.py` | 分隔线/代码块背景 | 极特殊，仅此使用 |
| `task_card.py` | `#FF000015` 逾期标签 | 含 alpha 通道，极特殊 |
