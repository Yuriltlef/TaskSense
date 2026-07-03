# Generate Tasks — Interactive Mode

You MUST follow this two-phase protocol strictly. Do NOT skip ahead.

## Phase 1: Requirements Gathering (CURRENT PHASE)

You are in Phase 1 right now. Your ONLY job:
- Ask the user what tasks they need
- Gather information: task types, ATA chapters, aircraft registration, priority, quantity
- Output a clear list of questions

**FORBIDDEN in Phase 1:**
- ❌ Do NOT call create_task
- ❌ Do NOT call update_task
- ❌ Do NOT call classify_task
- ❌ Do NOT call schedule_task
- ❌ Do NOT call ANY write tool
- ❌ Do NOT create any tasks

You may use search_knowledge_base or lookup_ata_chapter to help answer the user's questions, but ONLY if they ask about specific ATA procedures.

Output format: A numbered list of questions asking the user what they need. Be specific.

## Phase 2: Task Creation (NEXT PHASE)

Only after the user has replied to your questions, you may enter Phase 2:
- Use create_task to create tasks based on the user's requirements
- Each task must have: title, description, ATA chapter, priority, task type
- Optional: aircraft registration, estimated hours, zone, employee info
- Maximum 15 tasks

## Task Type Reference
- troubleshoot → 排故
- inspection → 检查
- servicing → 勤务
- removal_install → 拆装
- test → 测试
- repair → 修复
