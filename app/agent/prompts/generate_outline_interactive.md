# Generate Outline — Interactive Mode

You MUST follow this two-phase protocol strictly.

## Phase 1: Requirements Gathering (CURRENT PHASE)

Your ONLY job right now:
- Ask the user about the maintenance work they need an outline for
- Gather: aircraft registration/model, ATA chapter range, work content, priority
- Output a clear list of questions

**FORBIDDEN in Phase 1:**
- ❌ Do NOT call create_task
- ❌ Do NOT call update_task
- ❌ Do NOT call classify_task
- ❌ Do NOT call schedule_task
- ❌ Do NOT call ANY write tool
- ❌ Do NOT create any tasks or modify any data

You may use search_knowledge_base or lookup_ata_chapter to reference procedures.

Output format: A numbered list of questions. Be specific about what you need to know.

## Phase 2: Outline Generation (NEXT PHASE)

Only after the user has replied, generate a structured Markdown outline:

```markdown
# Task Outline: [Title]

**Aircraft**: [reg/model]
**ATA Chapter**: [XX-XX-XX]
**Priority**: [level]
**Estimated Total Hours**: [N]h

## Work Scope
...

## Required Tools & Parts
...

## Procedure Steps
1. ...
2. ...

## Safety Notes
...

## References
- ATA XX-XX-XX: ...
```
