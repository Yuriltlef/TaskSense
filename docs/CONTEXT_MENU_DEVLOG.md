# 右键菜单开发日志与踩坑记录

## 概述
2026-07-04，为 TaskSense 看板任务卡片添加右键菜单功能，实现按列分级菜单 + 单任务 AI 工具 + 取消流程重构。

## 踩坑记录

### 1. Flet 0.28.3 overlay 不支持 expand
`page.overlay` 中的控件无父布局分配尺寸，`expand=True` 无效。必须显式设置 `width=page.width, height=page.height`。

```python
# 错误
Stack([dimmer, panel], expand=True)

# 正确
Stack([dimmer, panel], width=page.width, height=page.height)
```

### 2. 透明 overlay 不接收点击事件
`Container(bgcolor=BLACK, opacity=0.0)` 在 Flet 0.28.3 中不参与 hit-testing，点击穿透到底层控件。**不能用透明遮罩关闭菜单**。

**解决方案**：协作式关闭——在卡片点击、Esc 键、再次右键、看板刷新时主动调用 `close_current_menu()`。

### 3. GestureDetector.on_secondary_tap 不带坐标
右键事件的 `e.data` 为空字符串，`e.local_x`/`e.global_x` 等属性不存在。只有 `on_tap_down`（左键）事件带坐标。

**解决方案**：Windows 下用 Win32 API `GetCursorPos` + `ScreenToClient` 实时获取鼠标客户区坐标。

```python
pt = wintypes.POINT()
ctypes.windll.user32.GetCursorPos(byref(pt))
hwnd = ctypes.windll.user32.FindWindowW(None, "TaskSense")
if hwnd:
    ctypes.windll.user32.ScreenToClient(hwnd, byref(pt))
```

### 4. AlertDialog modal=False 不渲染
`page.dialog = AlertDialog(modal=False)` 在 0.28.3 中不显示。必须用 `page.open(AlertDialog(modal=True))` 或 `page.overlay` 手动布局。

### 5. Container.on_long_press ≠ 右键
Flet 桌面上 `on_long_press` 是真正的长按（~500ms），不是右键。要捕获右键需用 `GestureDetector.on_secondary_tap`，但需放在 `Draggable` 内部（外层 `Draggable` 消费事件会导致内层 GestureDetector 收不到右键）。

### 6. Agent 取消检查不全（关键 Bug）
`_agent_loop` 在 LLM 直接回答（无工具调用）时 `return resp_text` 跳过了取消检查。导致 `cancel_event.set()` 后 LLM 回应仍被当正常结果。

**全部 6 个路径必须检查**：
- 循环入口前 ✅
- 每轮开始时 ✅  
- LLM 返回 `[Error]` 时 ✅（补）
- 无工具调用直接回答时 ✅（补）
- 达到最大轮次时 ✅（补）
- 工具执行前/中 ✅
- 兜底路径 ✅（补）

### 7. cancel_event 跨线程 None 安全
`self.ai_chat._cancel_event` 可能被 `hide_task_card()` 置为 None。后台线程用 `getattr(self.ai_chat, '_cancel_event', None)` 安全获取，`cancel.is_set()` 前必须 `cancel and cancel.is_set()`。

### 8. 幽灵卡片生命周期
- AI 工具调用 `classify_task` 等 → 设置 `ai_proposed=True` → 看板渲染幽灵卡片
- 用户接受/拒绝 → `_accept_ai_task` / `_reject_ai_task` → 清除 `ai_proposed`
- 取消时 → `_force_clear_all_ghosts` 清除所有 AI 标记
- 批量工具取消清全部，单任务取消只清指定任务

### 9. AI 提示词强制工具调用
LLM 有时跳过工具调用直接返回文本。提示词需用强制性语言：
- "locked task — you MUST complete it"
- "Required Actions — MANDATORY"
- "If you do NOT call this tool, the task will fail"

### 10. 弹窗按钮风格统一
所有弹窗的按钮使用相同 `ButtonStyle`：
```python
btn_st = ft.ButtonStyle(
    shape=RoundedRectangleBorder(radius=s(6)),
    padding=only(left=s(18), top=s(7), right=s(18), bottom=s(7)),
    text_style=TextStyle(size=s(12)),
)
# 取消: OutlinedButton + border side
# 确定: ElevatedButton + bgcolor + elevation=0
```

### 11. 右键菜单弹出方向
窗口底部弹出菜单可能被截断。需计算菜单估算高度，下方空间不足时向上弹出：
```python
est_h = item_count * 36 + divider_count * 12 + 8
if y + est_h > ph - 8:
    menu_y = y - est_h - 4  # 光标上方
```

### 12. 看板刷新时关闭菜单
预加载完成、状态变更等触发 `_refresh_board` → 必须先 `close_current_menu()`，否则 overlay 孤儿。

## 关键文件

- `app/ui/widgets/context_menu.py` — 右键菜单组件（overlay 定位 + 确认框 + 弹出动画）
- `app/ui/pages/board_page.py` — 9 列菜单构建器 + `_card_action` 动作分发 + `_run_ai_action` 通用 AI 流程
- `app/ui/components/kanban_column.py` — GestureDetector 右键触发 + Win32 坐标
- `app/ui/components/task_card.py` — 移除 on_long_press，右键由外层 GestureDetector 处理
- `app/agent/orchestrator.py` — `_agent_loop` 全部取消检查点
- `app/agent/prompts/classify_single.md` 等 5 个新提示词文件
- `app/ui/services/agent_service.py` — 5 个新单任务 Service 方法
- `app/ui/components/ai_chat.py` — `__AI_ONLY__` 前缀 + `_cancel_task` 修复
