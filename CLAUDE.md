# BP Tracker — Claude Code Instructions

## Memory
Before ending any session (when the user says goodbye, closes, or wraps up),
always update `/Users/ubd/.claude/projects/-Users-ubd-Library-Mobile-Documents-com-apple-CloudDocs-Projects-01-UTI-bp-tracker/memory/MEMORY.md`
with anything new: decisions made, bugs fixed, features added, gotchas discovered.
Keep it current so the next session starts fully informed.

## Workflow
- Always commit and push to git after every code change.
- Use `uv run` — never `pip` or bare `python`.
- After pushing: remind the user to run `cd /home/ubd/bp_tracker && git pull && sudo systemctl restart bp-tracker` on the VPS.

## Style
- Concise. No fluff.
- No medication names in any git-tracked file (privacy).
