<!-- BEGIN:AGENT_MEMORY_POLICY (do not edit this block) -->
# Agent Memory Policy
<!-- policy_version: 1.0 | generated: 2026-07-02T11:46:27Z | server: memory-engine -->

## Purpose

This policy preserves reliable project context while preventing memory pollution.
All compliant MCP coding agents operating in this project MUST follow this workflow.

The MCP server cannot technically force every arbitrary client or model to invoke
tools. This policy provides strong workflow guidance for clients that honour
project-level instructions.

---

## Task Classification

Treat a task as **non-trivial** if it involves any of:

- Editing production code, tests, build scripts, CI, dependencies, schemas, or configuration
- Changing public APIs or interfaces
- Debugging a defect or investigating a failure
- Changing security, authorization, validation, retry, state-machine, or persistence behaviour
- Modifying multiple files
- Making a design or architecture decision
- Refactoring behaviorally meaningful code
- Working on branch-specific implementation

Treat a task as **trivial** only when clearly limited to:

- Spelling correction
- Comment-only wording change
- Formatting-only change
- Pure explanation with no repository modification
- A user-requested one-line non-behavioral edit

**When uncertain, classify the task as non-trivial.**

---

## Mandatory Pre-Task Recall Rule

Before editing files for any non-trivial task, the agent **MUST** call
`memory-engine:retrieve_agent_context`.

The agent MUST provide:
- a concise task description
- affected files, modules, or symbols when known
- `task_intent` when supported (e.g. `bug_fix`, `architecture_review`, `feature_implementation`)
- current branch context when relevant

The agent MUST inspect returned constraints, incidents, decisions, source evidence,
branch scope, revision state, and retrieval trace before making behaviorally
meaningful changes.

---

## Mandatory Post-Task Reflection Rule

After a non-trivial task has been implemented and validation has passed, the agent
**MUST** call `memory-engine:reflect_and_write`.

The reflection MUST include:
- task summary and implementation changes
- files and modules changed
- validation performed (test commands and outcomes)
- whether the task succeeded, failed, was reverted, or remains unverified
- branch and revision context when available
- durable lessons, constraints, incidents, procedures, or decisions worth retaining

**Rules:**
- Do not claim successful validation when no validation ran.
- Do not write speculative or unverified facts as durable memory.
- Do not call failed or reverted work verified.
- If validation fails, only submit reflection if a useful failure record exists.

---

## Source-of-Truth and Safety Rules

Memory is advisory context — not stronger authority than current source code,
tests, configuration, or user requirements.

When memory conflicts with verified current source evidence:
- Prefer verified current evidence.
- Report the conflict.
- Allow the lifecycle system to mark memory stale, supersede it, or request review.

Never expose secrets, credentials, tokens, private keys, remote URLs, or user
identity information through memory content.

Never bypass path sandboxing, symlink protection, or Git safety restrictions.

---

## Branch-Aware Rules

- Current-branch memory should be preferred for current-branch work.
- Feature-branch memory must not be treated as mainline truth unless explicitly promoted.
- Historical, stale, archived, and superseded memory must not silently override
  current revision evidence.

---

## Retrieval Granularity Rules

| Situation | Preferred retrieval |
|---|---|
| Exact constraints or security rules | `proposition`-level, `proposition_types=["security_rule","constraint","risk"]` |
| Implementation questions | Paragraph or symbol-local context |
| Architecture questions | Module or document summaries, then supporting evidence |
| Debugging / change-impact | Current-branch, changed-file, and incident context |

Pass `task_intent` to `retrieve_agent_context` to activate granularity routing:

```
task_intent = "bug_fix"            # → propositions first
task_intent = "architecture_review" # → module summaries first
task_intent = "feature_implementation" # → paragraphs + propositions + summaries
```

---

## Compliance Checklist

**Before non-trivial work:**
- [ ] Called `retrieve_agent_context`
- [ ] Reviewed memory and source evidence
- [ ] Checked branch/revision relevance

**After successful validated non-trivial work:**
- [ ] Ran appropriate validation
- [ ] Called `reflect_and_write`
- [ ] Reported actual verification status
- [ ] Avoided speculative memory writes

---

## Transparency Notice

This policy is a project instruction for MCP-aware coding agents.
It provides strong workflow guidance for clients that honour project rules.
The MCP server cannot technically force every arbitrary client or model to invoke tools.

Policy version: 1.0
Project root: /home/hermes-workspace/rab9
MCP server: memory-engine
<!-- END:AGENT_MEMORY_POLICY -->
