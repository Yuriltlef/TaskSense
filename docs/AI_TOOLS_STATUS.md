# AI 工具实现状态 & 已知 Bug

最后更新：2026-07-03

---

## 7 个 AI 工具状态

| # | 工具 | 状态 | 触发 | 离线降级 |
|---|------|------|------|---------|
| 1 | 生成大纲 | ✅ 基础可用 | 菜单/弹窗 | 关键词推断 + 模板 |
| 2 | 生成任务 | ✅ 基础可用 | 菜单/AI 面板 | 提示配置 API Key |
| 3 | 自动分类 | ⚠️ 框架完成 | 菜单/AI 面板 | 列出任务 + 提示 |
| 4 | 自动排程 | ⚠️ 框架完成 | 菜单/AI 面板 | 列出任务 + 提示 |
| 5 | 自动验收 | ✅ 基础可用 | 菜单/AI 面板 | 列出任务 + 提示 + 复用 review_submission |
| 6 | 生成报表 | ✅ 基础可用 | 菜单/弹窗 | board_service 统计 |
| 7 | 任务审核 | ✅ 基础可用 | 菜单/弹窗 | 基本合规检查 |

---

## 已知 Bug & 待改进

### 🔴 严重
- **AI 创建任务后幽灵卡片偶尔不显示** — `_render_ai_ghost_cards` 在 `render_board` 后调用，但 board refresh 可能覆盖。需改为列级幽灵卡注入。
- **LLM 调用无超时保护** — 已加 30s timeout，但部分网络环境下仍可能阻塞 UI。需改为异步 + loading 状态。
- **分类/排程/验收的 Agent 调用未正确传递看板上下文** — 当前 `_run_agent_cmd` 只发通用的提示词，没有拼接实际待处理任务列表。

### 🟡 中等
- **AI 工具结果展示不一致** — 部分在弹窗、部分在 AI 面板。应统一为弹窗（报表/大纲/审核）和 AI 面板+幽灵卡（任务生成/分类/排程）。
- **对话气泡内的接受/拒绝按钮在刷新后丢失状态** — `_rebuild_bubbles` 重建整个聊天历史时，提案行的 accept/reject 结果被重置。
- **内联自动补全的 Agent 调用无防抖** — `AICompletionService.on_input_changed` 虽用了 `threading.Timer` 防抖，但 Agent 仍可能在快速输入时堆积请求。
- **员工匹配在创建任务弹窗中仍是弱匹配**（改了 ID 字段但名称未联动验证）。

### 🟢 轻微
- **AI 菜单按钮位置偶尔不准确**（在不同窗口大小下）。
- **日志文件按时间戳命名导致大量文件**（需加定期清理）。
- **创建任务弹窗中 ATA 字段无 GhostTextField 增强**（仅有标题字段有 AI 补全）。

---

## 内联工具状态

| # | 工具 | 状态 | 备注 |
|---|------|------|------|
| 1 | 内联自动补全 | ⚠️ 部分实现 | 标题+描述有 GhostTextField，ATA 字段缺失；Agent 调用不稳定 |
| 2 | 定期合规审查 | ❌ 未实现 | 计划在 Phase 5B |
| 3 | 增量操作 RAG | ❌ 未实现 | 计划在 Phase 5C |
| 4 | 验收态任务审核 | ✅ 基础可用 | 侧边栏 AI 审核区域，调用 review_submission Agent 工具 |

---

## review_submission 任务提交审核工具

### 定位
企业版功能 — 对验收中任务的提交材料进行 AI 智能审核。

### 架构
```
侧边栏「AI 建议」按钮                    菜单「自动验收」
       ↓                                        ↓
AgentService.review_submission(task_id)    AgentService.auto_acceptance()
       ↓                                        ↓
_build_submission_context(task) ─── 共享 ──→ review_submission.md prompt
       ↓                                        ↓
  单任务评估                             批量评估（每个任务同标准）
  {recommendation, reasons,              {同格式 × N}
   confidence, risk_level, ...}
```

### 审核维度
1. 完整性 — 必填字段、交接班日志、检查清单
2. 合规性 — AMM/AD/SB 引用（Agent 会搜索知识库）
3. 质量 — 日志详细程度（做了什么、发现了什么、遗留什么）
4. 安全性 — RII 签署、MEL 条目

### 输出格式
```json
{"recommendation": "approve|reject|need_more_info", "confidence": 0.85,
 "summary": "...", "reasons": [...], "missing_items": [...],
 "compliance_notes": "...", "suggested_actions": [...], "risk_level": "low|medium|high"}
```

### 离线降级
LLM 不可用时自动执行基本合规检查：日志缺失、ATA/注册号、RII 签署、
工时偏差、检查清单完成度。

### 复用说明
`AgentService._build_submission_context(task)` 和 `review_submission.md` prompt
被侧边栏和批量自动验收 tool 共用，确保审核标准一致。

---

## AI 工具架构

```
用户触发 (菜单/搜索/Ctrl+K)
  → board_page._run_agent_command(cmd)
    → 大纲/报表/审核 → 弹窗 ModalDialog + 异步后台线程
    → 任务/分类/排程/验收 → AgentService 方法 → Agent.ask() → LLM
      → LLM 调用 write_tools (create_task/classify_task/schedule_task)
        → 创建 ai_proposed=True 任务
          → board_page._render_ai_ghost_cards → AIGhostCard 幽灵卡片
          → ai_chat._build_proposal_actions → 对话气泡接受/拒绝
```
