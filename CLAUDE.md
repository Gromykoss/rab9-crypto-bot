<!-- grove:start -->
## Code navigation: grove for structure, shell for the rest

**grove** is a tree-sitter engine for *structural* code questions — byte-precise,
token-cheap (languages: json, python). Its tools are **deferred** MCP tools; load them in
one ToolSearch when a code question lands (don't default to a search agent or grep):
`mcp__grove__outline`, `mcp__grove__symbols`, `mcp__grove__source`, `mcp__grove__callers`, `mcp__grove__definition`, `mcp__grove__map`, `mcp__grove__check`.

**Use grove for named symbols and relationships** (every result carries a stable
`symbol-id`, `<lang>:<relpath>#<name>@<row>`, to pass forward; lines 1-based):
- What's in a file (skeleton, not the whole file) → `mcp__grove__outline` (`detail:0` if > 500 lines).
- Where a fn / type / struct / macro is defined → `mcp__grove__symbols` with `name` → `mcp__grove__source` with the id.
- One symbol's exact body → `mcp__grove__source`.
- Who calls it → `mcp__grove__callers`.
- Go-to-def from a usage (scope-aware, follows imports cross-file) → `mcp__grove__definition` with `at` (file:line:col).
- How a directory connects → `mcp__grove__map` (one call; prefer over many `mcp__grove__source`).
- Syntax after an edit → `mcp__grove__check`.

**Use the shell — the right tool, not a fallback — when grove can't see the target:**
- Text, not a symbol (a string, log / error message, config key, a macro's *value*,
  a constant, a flag, a TODO) → `grep -rn` / `rg`. grove finds definitions, not text.
- Non-code files (Makefiles, configs, data, docs) → `grep` / `read`.
- A quick fact (path exists, `ls`, `wc -l`, `find`, read a small file) → shell.

**Combine** (same 1-based lines, same bytes): `grep` a literal's line → `mcp__grove__definition`
`at` to resolve its symbol · `mcp__grove__outline` → bounded `read` (`offset`/`limit`) for
adjacent symbols · `mcp__grove__map` / `mcp__grove__symbols` to locate → `grep` a constant inside.

Rule of thumb: want a **symbol** → grove first (don't `grep` / `read` for it). Want
**text or a quick fact** → shell. Combining is fine.
<!-- grove:end -->

<!-- BEGIN:MEMORY_ENGINE_POLICY (do not edit this block) -->
## Memory Engine — Agent Workflow Policy

This project uses [Agent Memory Engine](https://github.com/uudam42/agent-memory-engine)
for persistent coding memory. Follow these rules exactly.

### `memory-engine:seed_project_context` — ONCE on new project setup

Call **once** when first connecting a project to Memory Engine (empty memory database).
Provide: `description`, `constraints`, `decisions`, `tech_stack`, `conventions`.
All fields optional — README.md is auto-scanned if description is omitted.
Do NOT call on every task. Check `memory_status` active_memories > 0 to skip.

### `memory-engine:retrieve_agent_context` — BEFORE non-trivial work

**Call when the task involves any of:**
- Editing production code, tests, CI, build scripts, dependencies, or config
- Debugging a failure or investigating unexpected behaviour
- Touching a subsystem not visited yet in this session
- Changing ≥ 2 files, or any design / architecture decision
- Security, auth, schema, retry, state-machine, or persistence logic

**Skip when ALL of these are true:**
- Pure explanation with no file edits planned
- Single-file, single-line typo / whitespace fix with no logic change
- Already called for the same task in this session

Pass `task_intent` for better results: `bug_fix`, `feature_implementation`,
`architecture_review`, `refactor`. Include `current_files` and `current_symbols`.

### `memory-engine:reflect_and_write` — AFTER verified non-trivial work

**Call when ALL of these are true:**
- `verification_status` is `tests_passed` or `build_success`
- ≥ 2 files changed, OR a non-trivial architectural decision was made
- Task is complete — not exploratory, not partially done

**Skip when ANY of these is true:**
- Tests failed or the task was reverted
- Only a single trivial file changed (typo, comment wording)
- Work is exploratory / no committed changes
- No validation was run

Pass `task_intent` (same value used in retrieve) and `changed_files` list.
Do NOT inflate `verification_status` — report what actually ran.

Full policy: `/home/hermes-workspace/rab9/.memory-engine/generated/AGENT_MEMORY_POLICY.md`
<!-- END:MEMORY_ENGINE_POLICY -->
