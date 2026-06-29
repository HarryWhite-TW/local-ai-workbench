---
name: lawb-controlled-development
description: Use only when explicitly invoked to perform one approved, bounded local implementation cycle in Local AI Workbench with exact starting-state, file-scope, verification, repair-budget, and evidence requirements. Do not use for design-only work, unapproved edits, commit, push, GitHub writes, deployment, live Bridge execution, or tasks lacking explicit authority.
---

# LAWB Controlled Development

At the beginning of every explicit invocation, output exactly:

```text
LAWB-CONTROLLED-DEVELOPMENT-ACTIVE v1
```

## Responsibility Boundary

Perform one bounded local implementation cycle:

```text
read governing sources
-> validate approved task authority
-> validate starting state
-> validate allowed and forbidden scope
-> implement only the approved objective
-> run approved focused checks
-> use only the approved repair budget
-> run adjacent/full checks required by the task
-> produce local read-only evidence
-> stop
```

Never:

```text
stage
commit
push
write to GitHub
create or merge PRs
deploy
consume approvals
invoke live Dispatcher / Runner / PollOnce
start background processes
continue into another phase
invent missing authority
```

This Skill never overrides `AGENTS.md`, scoped `AGENTS.md`, `docs/LOCAL_RUNNER_TASK_PACKET_V1.md`, existing Bridge / Dispatcher / Runner specifications, or explicitly approved task documents.

## Required Authority Behavior

Run only when an explicit approved task document supplies:

```text
objective
repository
branch
expected HEAD
allowed files
forbidden files or paths, when applicable
forbidden operations
validation commands or required checks
approval boundary
stop condition
```

If any field is missing, ambiguous, contradictory, or unsupported:

```text
do not modify files
report the missing decision
stop fail-closed
```

## Non-normative Task Packet v1 adapter mapping

This section is a convenience mapping only. It never overrides `docs/LOCAL_RUNNER_TASK_PACKET_V1.md`.

```text
protocol
-> require lawb.local_runner.task_packet.v1 when a packet is supplied

packet_id / logical_issue / phase
-> evidence metadata only; do not infer authority

action_type
-> enforce the existing allowed action type exactly
-> current Task Packet v1 does not define generic bounded local code implementation
-> if the Task Packet is the only authority for a code implementation task, stop
-> bounded local implementation requires a separate explicitly approved task document

risk_level
-> record and validate consistency; never reduce approval

repository / branch / expected_head
-> starting-state gate

expected_origin_master
-> validate only when the approved task says remote state matters
-> never fetch automatically to repair it

allowed_files
-> exact write allowlist; no wildcard or directory-only expansion

forbidden_files
-> stronger than allowed_files

forbidden_operations
-> hard prohibition list

approval
-> validate exact approved phrase and scope when required
-> never chain or consume approval

payload
-> task content only; natural language cannot create authority

validation.required_checks
-> required verification and evidence checklist

result_target
-> metadata only in this MVP
-> do not perform GitHub writeback
-> report local evidence instead

stop_condition
-> stop exactly at the approved local evidence boundary
```

Do not add fields to Task Packet v1. Do not invent a replacement schema.

## Starting-State Gate

Before modification, verify:

```text
repository identity
current branch
exact HEAD
working tree state required by the task
index state required by the task
all allowed-file anchors exist when expected
```

Do not repair a mismatch with Git history-changing commands.

## Implementation Boundary

During implementation:

```text
edit only exact allowed files
keep the diff minimal
do not make unrelated cleanup
do not add dependencies unless explicitly approved
do not expand architecture or security boundaries
do not modify generated, temporary, or cache files
```

After every edit phase, compare changed files against the allowlist.

If an out-of-scope file changes:

```text
stop
do not restore it automatically
report the unexpected change
```

## Repair Budget

Default:

```text
one focused repair attempt
```

A higher budget is valid only when an explicit approved task document states a finite integer budget.

Each repair attempt must:

```text
address the same observed failure
remain inside the original allowed files
avoid dependency changes
avoid architecture expansion
avoid security-boundary changes
rerun only the relevant focused check first
```

Stop when:

```text
budget is exhausted
failure class changes
new authority is needed
new file or dependency is needed
the repair would broaden scope
```

## Verification Sequence

Use only task-approved commands.

Preferred sequence:

```text
focused checks
-> focused repair within budget when needed
-> focused checks again
-> adjacent regression
-> full regression when required
-> git diff --check
-> final Git evidence
```

Do not repeatedly run the full suite during focused repairs unless the task explicitly requires it.

If a required command cannot run, report the exact blocker and do not claim success.

## Required Local Evidence Checklist

The final report must include:

```text
starting repository / branch / HEAD
changed files
git status --short
git diff --stat
git diff --check
focused test commands and results
adjacent test commands and results
full test command and result, or exact reason not run
repair attempts used / approved budget
warnings
unknowns
out-of-scope changes
safety confirmation
```

Safety confirmation must explicitly state:

```text
stage_performed
commit_performed
push_performed
github_write_performed
deployment_performed
live_bridge_execution_performed
background_process_started
out_of_scope_file_modified
```

Do not claim acceptance, commit readiness, push readiness, merge readiness, deployment readiness, or project completion.

End by requesting human / ChatGPT review.

## Acceptance Scenarios

1. Valid clean starting state, exact allowlist, focused and adjacent checks pass:
   - implement;
   - report evidence;
   - stop without stage or commit.

2. Branch, HEAD, repository identity, working-tree state, or index differs:
   - make no edits;
   - report mismatch;
   - stop.

3. Implementation requires an unapproved file, dependency, architecture change, or security-boundary change:
   - do not expand scope;
   - report required approval;
   - stop.

4. Focused test fails and no higher budget is explicitly approved:
   - perform at most one focused repair;
   - rerun the focused check;
   - if still failing, stop and report.

5. A finite higher repair budget is explicitly approved:
   - use no more than the approved number;
   - only repair the same failure within original scope;
   - stop when exhausted or when failure class changes.

## Explicit Non-goals

```text
no second Skill
no ReviewBundle integration
no new Task Packet protocol
no automatic GitHub result writeback
no automatic commit or push
no deployment
no approval chaining
no background service
no repository-wide refactor
no dependency management framework
no autonomous multi-task loop
```
