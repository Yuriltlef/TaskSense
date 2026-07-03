# Phase 5 实现计划

## 状态：未开始

---

## 5A. 全局搜索完善（BL.md #8）

**目标**：搜索框支持所有 AI 命令和日志查询。

### 实现内容
- `/outline`、`/classify`、`/schedule`、`/acceptance`、`/review`、`/report` 命令
- `/log` 或 `搜索日志` — 查询操作日志
- 搜索结果展示在 AI 对话面板
- 搜索框下拉建议列表（随着输入自动匹配命令）

### 涉及文件
- `app/ui/pages/board_page.py` — `_on_search_submit`、`_do_command`
- `app/ui/components/command_bar.py` — 添加 AI 命令项

---

## 5B. 定期合规审查（AGENT_TOOLS 内联 #2）

**目标**：后台定时检查任务合规性。

### 实现内容
- 在 `BoardScheduler` 中新增定时审查逻辑（每 30 分钟）
- 检查维度：时间冲突、逾期任务、阻塞超时、字段缺失
- 发现问题 → 通知气泡 + 日志记录
- 生成审查报告

### 涉及文件
- `app/core/services/board_scheduler.py` — 新增 `_run_compliance_check()`
- `app/ui/widgets/notification_bubble.py` — 审查结果通知

---

## 5C. 增量操作 RAG（AGENT_TOOLS 内联 #3）

**目标**：将操作日志编码进知识库，Agent 可检索历史。

### 实现内容
- 创建独立 ChromaDB collection `kb_operations`
- 每个操作日志 → 嵌入编码 → 写入 collection
- 新增搜索工具 `search_operation_log`
- EventBus 事件 → 自动编码

### 涉及文件
- `app/knowledge/operation_store.py`（新建）
- `app/agent/tools/search_tools.py` — 新工具
- `app/core/events.py` — 监听日志事件

---

## 5D. AI 对话 UI 重构（AGENT_UI.md）

**目标**：对话面板现代化，参考 IDE AI 助手设计。

### 实现内容
- 用户消息即时显示（当前有延迟）
- 工具调用过程可视化（"正在检索知识库..."）
- 思维链可折叠展开
- 响应式宽度、文本选择
- 每条 AI 回复下方快捷操作栏：刷新/复制

### 涉及文件
- `app/ui/components/ai_chat.py`
- `app/ui/components/chat_bubble.py`

---

## 5E. E2E 测试

**目标**：端到端集成测试。

### 测试场景
1. 完整任务生命周期 create→classify→schedule→auto-ready→in_progress→inspection→complete
2. 阻塞/解阻塞流程
3. 拖拽限制（验证非法拖拽被拒绝）
4. AI 幽灵卡接受/拒绝
5. 日志生成与查询

### 涉及文件
- `tests/test_integration/test_board_flow.py`（新建）
- `tests/test_integration/test_agent_flow.py`（新建）
