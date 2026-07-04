# Classify Single Task

You are classifying a single backlog task. **This is a locked task — you MUST complete it.**

## Required Action — MANDATORY
You MUST call the `classify_task` tool exactly once with:
- `task_id`: the task ID from the details below
- `priority`: one of aog / cat_a / cat_b / cat_c / cat_d

If you do NOT call this tool, the task will fail. Do NOT skip the tool call.

## Priority Guidelines
- **AOG**: Aircraft grounded, immediate safety issue, MEL "no dispatch"
- **Cat A**: Must be addressed same day / before next flight
- **Cat B**: Must be addressed within 72 hours
- **Cat C**: Planned work within 240 hours, routine inspection
- **Cat D**: Deferrable up to 2880 hours, cosmetic or non-essential

## Instructions
1. Read the task details below carefully
2. Determine the correct priority based on task type, ATA chapter, and description
3. Call `classify_task` tool with the task ID and priority
4. After the tool call, briefly explain your reasoning (1-2 sentences)
