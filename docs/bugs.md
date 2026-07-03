# Bug 记录 — 自动验收功能修复

日期: 2026-07-03

---

## Bug 1: 任务审核弹窗打不开

**现象**: 点击 AI 工具菜单"任务审核"，弹窗不出现，UI 没反应。

**根因**: `_do_cmd_review()` 先同步调用 `AgentService.task_review()`（内部 `_llm_task_review()` 走 `agent.ask()` LLM 调用，最多 4 轮工具调用 × 30s 超时 = 120s），**然后**才 `OverlayDimmer.open()`。对比正常工作的 `_cmd_report` 是先开弹窗再异步加载。

**修复**: 重写 `_cmd_review`，参照 `_cmd_report` 模式：
- 立即打开弹窗（显示 ProgressRing 加载动画）
- 后台线程执行 `task_review()`
- 线程完成后更新弹窗 UI（汇总统计 + 问题列表）
- 添加 `page.width or 1280` / `page.height or 900` 防御回退

**改动的文件**:
- `app/ui/pages/board_page.py` — `_cmd_review` 方法（原 `_cmd_review` + `_do_cmd_review`）

---

## Bug 2: 自动验收按钮逻辑不正确

**现象**: 
- 点"确认"→ 任务直接移到已完成，没有根据 AI 建议（approve/reject）决定目标列
- 点"拒绝"→ 任务被移到待处理（backlog），不在验收中保留

**期望**: 
- 点"确认"→ approve → 已完成，reject → 待处理
- 点"取消"→ 留在验收中，只清除幽灵标记

**根因**: `AIGhostCard._do_accept` 对 acceptance 类型固定 target="completed"；`_do_reject` 对 acceptance 类型 `move_task(tid, "backlog")`。

**修复**:
- `_do_accept`: 读取 `task_data["recommendation"]`，approve→completed, reject→backlog
- `_do_reject`: 不移动任务，只 `state.update_task(tid, ai_proposed=False, ai_acceptance_recommendation=None, ai_acceptance_reason=None)`
- 按钮标签: 验收类型显示"确认/取消"，其他类型保持"接受/拒绝"
- `_accept_acceptance` / `_reject_acceptance` 回调消息更新

**改动的文件**:
- `app/ui/widgets/ai_ghost_card.py` — `_do_accept`、`_do_reject`、`_build` 按钮标签

---

## Bug 3: Task 模型缺少验收字段 → 幽灵卡片类型退化

**现象**: 验收幽灵卡片实际被渲染为 `new_task` 类型，"确认"按钮走了 `create_task` 逻辑创建重复任务。

**根因**: `state.update_task()` 有 `if hasattr(task, key)` 守卫（`app/core/state.py:142`）。`acceptance_review` 工具设置 `ai_acceptance_recommendation` 和 `ai_acceptance_reason`，但 Task dataclass 没定义这两个字段 → `hasattr` 返回 False → **值被静默丢弃**。`_render_ai_ghost_cards` 读到 `None` → 类型退化为 `new_task`。

**修复**: Task 模型新增两个字段：
```python
ai_acceptance_recommendation: Optional[str] = None  # "approve" | "reject"
ai_acceptance_reason: Optional[str] = None
```
同步更新 `from_dict()` 和 `to_dict()`。

**改动的文件**:
- `app/core/models/task.py` — 字段定义、`from_dict`、`to_dict`

---

## Bug 4: 确认验收后任务"消失"

**现象**: 点"确认"→ approve 后任务被正确移到已完成列，但看板上看不见。

**根因**: `FilterState.show_completed` 默认 `False`。当有任何筛选条件激活时，`_apply_filters` 过滤掉已完成列任务。

**修复**: `_accept_acceptance` 和 `_reject_acceptance` 中调用 `board_service.set_filters(FilterState())` 清除筛选器，确保目标列可见。同时调用 `_navigate_to_task(tid)` 打开任务详情侧边栏。

**改动的文件**:
- `app/ui/pages/board_page.py` — `_accept_acceptance`、`_reject_acceptance`

---

## Bug 5: Agent 执行后幽灵卡片不显示

**现象**: 自动验收 Agent 调用 `acceptance_review` 工具成功设置了 `ai_proposed=True`，但看板上不出现幽灵卡片。

**根因**: `_run_agent_cmd` 在 Agent 返回后只调用了 `_show_ai_in_panel` 更新 AI 面板，没有刷新看板。`state.update_task` 不会触发 UI 刷新。

**修复**: `_run_agent_cmd` 的 `finally` 块中加入 `self._refresh_board()`，确保 Agent 工具调用产生的幽灵卡片被渲染。

**改动的文件**:
- `app/ui/pages/board_page.py` — `_run_agent_cmd`

---

## Bug 6: 数据残留问题

**现象**: `board_state.json` 存在重复任务（backlog 和 inspection 各有一份同一任务），验收中任务带着检查清单。

**根因**: 
- 旧版 `_do_reject` 把验收任务 move 到 backlog 造成重复
- 旧版 `load_demo_data` 给验收任务自动填充 5 项检查清单
- 持久化层每 5 秒自动保存，旧数据被反复写回

**修复**: 
- 手动删除 `board_state.json`（需先停 app）
- 移除 `load_demo_data` 中检查清单自动填充逻辑
- 清理 `__pycache__` 目录

**改动的文件**:
- `app/ui/pages/board_page.py` — `load_demo_data` 去掉 checklists
- `app/data/board_state.json` — 删除重建

---

## 涉及文件汇总

| 文件 | 改动内容 |
|---|---|
| `app/ui/pages/board_page.py` | `_cmd_review` 异步改造、`_run_agent_cmd` 加刷新、`_accept_acceptance`/`_reject_acceptance` 清筛选+导航、`load_demo_data` 去检查清单 |
| `app/ui/widgets/ai_ghost_card.py` | `_do_accept` 按建议移动、`_do_reject` 保留原位、按钮标签区分验收类型 |
| `app/core/models/task.py` | 新增 `ai_acceptance_recommendation`、`ai_acceptance_reason` 字段 |
| `app/data/board_state.json` | 清理重复数据和旧检查清单 |
