# TaskSense 开发指南

> 最后更新：2026-07-05（重构完成后）

## 项目架构

```
app/
├── agent/           LLM Agent 编排器 + 工具 + 提示词
│   ├── prompts/     20 个 .md 提示词文件
│   └── tools/       board_tools / search_tools / write_tools / task_state_tools
├── config/          常量 / 主题 / 设置 / ATA 关键词
├── core/            核心模型 / 状态管理 / 校验器 / 服务 / 日志
│   ├── models/      Task / Kanban / Aircraft / LogEntry
│   ├── services/    task_service / board_service / employee_service / persistence / log / scheduler
│   └── state.py     全局状态管理器（单一状态树）
├── knowledge/       RAG 知识库流水线
├── ui/
│   ├── app.py       应用入口（标题栏 + 窗口管理）
│   ├── components/  AI面板 / 看板 / 列 / 卡片 / 侧栏 / 底部状态栏 / 对话框
│   ├── controllers/ 看板控制器（UI ↔ Core 桥梁）
│   ├── dialogs/     **6 个弹窗（独立文件）**
│   ├── pages/       board_page（主页面协调层）/ 设置窗口
│   ├── services/    **7 个服务（AI命令/渲染/提案/取消/上下文菜单/弹窗工厂等）**
│   └── widgets/     幽灵文本 / 幽灵卡片 / Toast / 遮罩 / 右键菜单 / 通知气泡
├── data/            持久化数据（board_state.json / employees.json / logs/）
└── main.py          启动入口
```

## 加新功能指南

### 加新右键菜单动作

1. 在 `board_page.py` 的 `_init_action_handlers` 注册 1 行:
```python
"my_action": self._act_my_action,
```
2. 添加 1-3 行处理方法:
```python
def _act_my_action(self, tid, t):
    task_service.update_task(tid, my_field=value)
    Toast.show(self._page, "操作成功", "success")
```
3. 在 `ContextMenuBuilder` 对应列的方法里加菜单项

### 加新弹窗

1. 创建 `app/ui/dialogs/my_dialog.py`:
```python
import flet as ft
from app.ui.components.modal_dialog import ModalDialog
from app.ui.services.dialog_builder import header as dlg_header, footer as dlg_footer
from app.core.services.task_service import task_service

def open(page: ft.Page, tid: str):
    # 构建弹窗 UI
    body = ft.Container(...)
    content = ft.Column([
        dlg_header(ft.Icons.XXX, "标题", lambda e: dlg.close()),
        body,
        dlg_footer("取消", "确认", on_confirm, on_cancel=lambda e: dlg.close()),
    ], spacing=0, tight=True)
    dlg = ModalDialog(page, content, width=480)
    dlg.open()
```
2. board_page 加一行委托:
```python
def _dlg_my(self, tid):
    from app.ui.dialogs.my_dialog import open as dlg_my
    dlg_my(self._page, tid)
```

### 加新 AI 工具

1. 写 prompt 文件 `app/agent/prompts/my_tool.md`
2. 在 `agent_service.py` 加方法（如需要新 API）
3. 在 `ai_commands.py` 加 `_cmd_my_tool()` 方法
4. 在 `ai_commands.py` 的 `dispatch()` 注册
5. 在 AI 菜单（`app.py`）加入口按钮

### 加新看板列

1. `constants.py`: ALLOWED_TRANSITIONS / DEFAULT_COLUMNS 加列定义
2. `ContextMenuBuilder`: 加 `_my_column()` 菜单方法
3. `TaskStatus` enum 加状态值

## 维护须知

### 取消流程（最易出问题区域）

取消有 9 条结束路径，核心规则：
- **取消处理器（主线程）更新 UI，后台线程不再重复更新**
- **所有 cancel 检测 → silent return（不调 _finish_task_card）**
- **添加新 AI 工具时，确保 cancel_event 检查覆盖所有退出路径**

### 幽灵卡生命周期

```
LLM调用工具 → ai_proposed=True → BoardRenderer渲染幽灵卡
→ 用户接受 → ProposalHandler.accept → 移动任务+清标记
→ 用户拒绝 → ProposalHandler.reject → 清标记/删任务
→ 用户取消 → CancelCoordinator → 清 ai_proposed
```

### Flet 0.28.3 限制（不可升级）

- `page.overlay` 不支持 `expand=True`
- `page.on_resized` 只触发 RESIZED（松开时），不触发 RESIZE（拖拽中）
- 遮罩使用页面内容树 Stack + expand 替代 overlay
- Container 不支持 `mouse_cursor`
- TextField 无 `focused_border`（但有 `focused_border_color`）
- 无 `PopupMenuButton`，右键菜单手动构建

### 日志系统

- 生产文件：`data/logs/tasksense.log`（固定名 + RotatingFileHandler，5MB × 5 备份）
- 启动时自动清理 7 天前旧文件（保留最近 20 个）
- `log.info("category", msg, **kwargs)` — 结构化键值对
- `log.warn/error` — 警告/错误级别

### 测试

- 311 测试，10 skipped（知识库加载耗时）
- 运行：`.venv/Scripts/python -m pytest tests/ -q`
- 添加新模块时同步加测试
