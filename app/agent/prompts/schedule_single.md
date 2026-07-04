# Schedule Single Task

You are scheduling a single triage task. **This is a locked task — you MUST complete it.**

## Required Actions — MANDATORY
1. Call `search_employees` to find a qualified technician
2. Call `schedule_task` tool exactly once with:
   - `task_id`: the task ID from the details below
   - `planned_start`: ISO datetime (e.g., "2026-07-05T08:00:00")
   - `planned_end`: ISO datetime
   - `employee_id`: the selected employee's ID
   - `employee_name`: the selected employee's name
   - `estimated_hours`: realistic hour estimate based on task type

If you do NOT call `schedule_task`, the task will fail. Do NOT skip the tool call.

## Instructions
1. Read the task details below
2. Use `search_employees` to find available, qualified personnel
3. Assign realistic time windows (consider task type and estimated hours)
4. Call `schedule_task` with the selected employee and time window
5. After the tool call, briefly explain your choices (1-2 sentences)
