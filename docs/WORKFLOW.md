# 看板工作流与状态转换规则

## 9 列看板流程

```
待处理 ─→ 分类中 ─→ 已排程 ─→ 就绪 ─→ 执行中 ─→ 验收中 ─→ 已完成 ─→ 已归档
  │        ↑│        ↑│        ↑│       │  ↑      │  ↑
  │        ││        ││        ││       │  │      │  │
  └────────┘└────────┘└────────┘│       │  │      │  │
                                │       ├─阻塞中──┘  │
                                │       │  │         │
                                └───────┘  └─────────┘
```

## 列定义

| id | 标题 | WIP 上限 | 顺序 | 可见 | 说明 |
|----|------|---------|------|------|------|
| `backlog` | 待处理 | - | 0 | ✓ | 新任务入口，等待分类评估 |
| `triage` | 分类中 | 10 | 1 | ✓ | 评估优先级和所需资源 |
| `scheduled` | 已排程 | - | 2 | ✓ | 分配时间窗口和人员 |
| `ready` | 就绪 | 20 | 3 | ✓ | 工具、手册、航材到位，随时开工 |
| `in_progress` | 执行中 | 15 | 4 | ✓ | 正在维修施工 |
| `inspection` | 验收中 | 15 | 5 | ✓ | 维修后质量检查 |
| `parts_hold` | 阻塞中 | 10 | 6 | ✓ | 缺航材，等待到货 |
| `completed` | 已完成 | - | 7 | ✓ | 维修完成，记录关闭 |
| `archived` | 已归档 | - | 8 | ✗ | 历史记录，默认隐藏 |

## 状态转换矩阵

```python
ALLOWED_TRANSITIONS = {
    "backlog":      ["triage", "archived"],        # 待处理 → 分类 / 直接归档
    "triage":       ["scheduled", "backlog"],       # 分类中 → 排程 / 退回待处理
    "scheduled":    ["ready", "backlog", "triage"], # 已排程 → 就绪 / 退回
    "ready":        ["in_progress", "scheduled"],   # 就绪 → 开工 / 撤回排程
    "in_progress":  ["inspection", "parts_hold", "completed"],  # 执行中 → 检查 / 缺件 / 直接完成
    "inspection":   ["completed", "in_progress"],   # 验收中 → 完成 / 返工
    "parts_hold":   ["ready", "scheduled"],         # 阻塞中 → 回到就绪 / 重新排程
    "completed":    ["archived"],                   # 已完成 → 归档
    "archived":     [],                             # 已归档 → 死胡同
}
```

## 被禁止的拖拽方向

| 方向 | 原因 |
|------|------|
| 待处理 → 已排程/就绪/执行中 | 跳过分类评估，不知优先级和资源需求 |
| 分类中 → 就绪/执行中 | 跳过排程，未分配时间窗口和人员 |
| 已排程 → 执行中 | 跳过就绪确认，工具航材是否到位未知 |
| 就绪 → 验收中/已完成 | 跳过执行，没干活不能检查 |
| 执行中 → 已排程/就绪/待处理 | 已开工，不可向前回退 |
| 阻塞中 → 待处理/分类中/执行中 | 零件到货后回到就绪或排程，不跳过步骤 |
| 已完成 → 除归档外任意列 | 合规要求，已完成不可重新激活 |
| 已归档 → 任意列 | 永久封存 |

## 允许的回退路径

- **分类中 → 待处理**：重新评估
- **已排程 → 分类中/待处理**：撤回排程
- **就绪 → 已排程**：撤回就绪
- **验收中 → 执行中**：检验不通过，返工
- **阻塞中 → 就绪/已排程**：零件到货，重新安排

## 同列重排序

同列内上下拖拽只改变显示顺序，不改变任务状态，因此绕过了 `ALLOWED_TRANSITIONS` 校验（`task_service.py:83` 行）。

## 拖拽视觉反馈

- **蓝色列边框** = 允许放入（`target_col in ALLOWED_TRANSITIONS[src_col]` 或同列）
- **红色列边框** = 禁止放入（不在允许列表中，松手静默拒绝）

## 相关代码

- `app/config/constants.py` — `DEFAULT_COLUMNS`、`ALLOWED_TRANSITIONS`
- `app/core/validators.py` — `TaskValidators.validate_transition()`
- `app/core/services/task_service.py` — `TaskService.move_task()`
- `app/core/state.py` — `AppState.move_task()`
- `app/ui/components/kanban_column.py` — 拖放实现、列高亮
