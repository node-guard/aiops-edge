---
description: Pick the next backlog task for the current sprint and plan it
argument-hint: "[sprint, e.g. S3] [owner A|B|J]"
---
Read CLAUDE.md, then docs/BACKLOG.md.

1. Using $ARGUMENTS (sprint and owner), list tasks with status `todo` whose dependencies are `done`. If no arguments, use the lowest sprint with open `M` tasks.
2. Recommend ONE task. Explain why in two lines.
3. For that task: restate acceptance criteria (3-5 bullets), list files you will touch, name tests you will write first, and flag any security boundary, schema change or ADR need.
4. Stop and wait for my approval before writing code.
