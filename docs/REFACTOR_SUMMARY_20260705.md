# 重构总结 — 2026-07-04/05

## 成果

```
34 次提交 | 311/311 测试 | 0 回归

board_page.py:  3538 → 1665 (-53%)
新增模块:       17 个
Bug修复:        10+
print→log:      全部迁移
```

## 新增模块

| 模块 | 行数 | 职责 |
|------|------|------|
| `ai_commands.py` | 430 | 7个AI命令 + 报表/审核弹窗 |
| `board_renderer.py` | 267 | 看板渲染 + 幽灵卡注入 |
| `dialog_builder.py` | 212 | 弹窗header/footer/button + 表单字段工厂 |
| `context_menu_builder.py` | 175 | 9列右键菜单 |
| `proposal_handler.py` | 174 | 幽灵卡接受/拒绝 |
| `ata_keywords.py` | 139 | ATA章节关键词推测 |
| `task_registry.py` | 88 | 线程安全任务注册表 |
| `cancel_coordinator.py` | 74 | 取消流程幽灵清除 |
| `ai_command_runner.py` | 53 | AI命令guard/setup/cancel |
| `json_extractor.py` | 48 | 4级JSON解析 |
| `log_manager.py` | 65 | 日志自动清理 |
| `cache_utils.py` | 25 | 模型缓存检查 |
| `dialogs/edit_dialog.py` | 508 | 编辑任务弹窗 |
| `dialogs/schedule_dialog.py` | 165 | 排程弹窗 |
| `dialogs/submit_dialog.py` | 79 | 提交验收弹窗 |
| `dialogs/priority_dialog.py` | 81 | 优先级弹窗 |
| `dialogs/filter_dialog.py` | 68 | 筛选弹窗 |
| `dialogs/block_dialog.py` | 54 | 阻塞弹窗 |

## 修复的 Bug

| Bug | 严重度 | 修复 |
|-----|--------|------|
| 键盘处理器冲突（Dialog关闭后Ctrl+K失效）| 🔴 | 删除monkey-patch |
| cancel=None泄漏（任务注册表残留）| 🔴 | _finish_task_card补全 |
| 取消后任务被误删 | 🔴 | ai_proposed检查 + call顺序 |
| update_task无白名单（LLM可改status）| 🔴 | 30字段白名单 |
| LLM调用不可中断 | 🟡 | Future轮询150ms |
| 取消后LLM重试覆盖"已取消" | 🟡 | cancel_event检查 |
| AI提案延迟显示 | 🟡 | _rebuild_chat_ui_sync |
| 取消后双重"已取消"卡片 | 🟡 | 后台线程silent return |
| 排程弹窗不保存planned_start/end | 🟡 | 添加updates字段 |
| 排程默认时间相同导致选同一天失败 | 🟡 | 08:00/17:00默认 |
| 完成时间未填时_recalc误判 | 🟡 | 跳过空时/分校验 |
| 编辑弹窗冻结字段出现在AI补全列表 | 🟡 | field_filter + _FIELD_LOCKS |
| WIP检查不一致(≥ vs >) | 🟡 | 统一为≥ |
| validate_create不校验aircraft_reg | 🟡 | 补齐校验 |
| state.move_task无验证守卫 | 🟡 | 添加validate_transition |

## 架构改进

- **17个独立模块** 替代 3538行上帝类
- **取消流程** 9条路径全覆盖
- **LLM安全** 白名单 + 可中断 + retry检查
- **遮罩** 原生布局实时响应缩放
- **弹窗** 独立文件，加弹窗=1文件
- **右键动作** 注册表模式，加动作=1行

## 代码规范

- 全部print→log迁移
- 内联import清理（19处→文件顶部）
- _reflash拼写修正
- IDE类型警告修复
- 死代码清理（_run_agent_cmd, _cmd_labels, AISuggestionPanel）
- 配置文件编码修复（UTF-16→UTF-8）
- 重复缓存检查提取（cache_utils）
- 重复ATA字典外置（ata_keywords）
- 重复表单工厂统一（dialog_builder）
