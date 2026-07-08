# Post-RV2-03 Workflow Optimization Contracts V1

## 1. Purpose

This document freezes the minimum contracts for the post-RV2-03 workflow optimization path. It is a documentation and schema boundary for OPT-01 only.

This document does not authorize implementation, commit, push, PR, Issue mutation, live Bridge execution, Dispatcher, Runner, Codex runtime execution, tool installation, dependency installation, service, watcher, MCP, or RV2-04.

The contracts below are intended to reduce repeated workflow overhead while preserving the repository-wide safety model, Bridge authority boundaries, and current-truth discipline.

## 2. Problem Being Solved

The workflow costs targeted by this contract are:

- repeated repo exploration
- oversized Codex task packets
- duplicated Git/test/GitHub checks
- fragile evidence capture
- false blockers
- current-truth confusion
- high-tier model used for mechanical work
- reviewer time spent locating evidence

The optimization target is better packaging and evidence, not broader authority.

## 3. Three-Layer Architecture

Layer 1 - Environment readiness: verifies that the local host, repository, Git identity, tools, and required read-only access are ready for the approved task class. This layer may identify host drift but must not silently repair it.

Layer 2 - Generic project execution gate: provides repository-native checks for task start, allowed paths, command execution records, diff checks, final Git state, and compact evidence. Layer 2 must not absorb live Bridge acceptance or remote write authority.

Layer 3 - Dedicated live acceptance harnesses: remains the place for separately approved live Bridge, Dispatcher, Runner, Codex, GitHub publication, and Primary Operational Host acceptance work.

Layer 2 may prepare evidence for review. It must not become a live Bridge harness, a remote writer, or an acceptance oracle for semantic product correctness.

## 4. Layered Task Packet Contract

A Layered Task Packet separates stable governance, current observations, and the task-specific delta so each task does not repeat all context.

Layer A - Governance Reference: points to stable source-of-truth files such as `AGENTS.md`, scoped `AGENTS.md` files, `PLANS.md`, Direction Lock, Bridge Operator specification, and task-specific governing docs. It should list references and required read audits. It must not duplicate full governing documents unless the task requires an excerpt for a narrow decision.

Layer B - Current-State Manifest: contains short-lived observed, declared, and derived current state for the specific task or gate. It should include Git state, relevant GitHub read state when available, tool visibility, auth availability, allowed paths, and invalidation rules. It must not be committed as current truth and must not be manually edited.

Layer C - Execution Delta: states the approved objective, allowed files, forbidden operations, validation commands, stop conditions, repair budget, and final report format for this specific task. It should contain only the delta needed to execute the approved work.

Task packets must avoid duplicating stable governance in every task body. They must also avoid treating generated or stale Layer B observations as durable repository truth.

## 5. Current-State Manifest Contract

The Current-State Manifest is a short-lived observation artifact generated per task or gate. It is not committed as current truth, not manually edited, and not a replacement for direct source-of-truth reads.

Required principles:

- generated per task or gate
- short-lived observation artifact
- not committed as current truth
- not manually edited
- separates observed, declared, and derived fields
- records sources and timestamps
- invalidates on Git, GitHub, auth, approval, or working-tree changes
- contains no secrets

Minimal schema:

- `schema`: manifest schema identifier
- `example_only`: `true` only for examples
- `generated_at_utc`: observation time
- `expires_at_utc`: maximum freshness time
- `scope`: repository and task identifiers
- `observed`: facts read from tools or files
- `declared`: facts supplied by the task packet or governing docs
- `derived`: computed comparisons or classifications
- `sources`: command, file, or issue references used for observations
- `invalidates_on`: state changes that make the manifest stale
- `safety`: secret-redaction and no-write assertions

Minimal JSON example:

```json
{
  "schema": "lawb.current_state_manifest.v0.1",
  "example_only": true,
  "generated_at_utc": "2026-07-08T00:00:00Z",
  "expires_at_utc": "2026-07-08T00:30:00Z",
  "scope": {
    "repo": "HarryWhite-TW/local-ai-workbench",
    "task_id": "OPT-01-example"
  },
  "observed": {
    "git": {
      "branch": "example-branch",
      "head": "0000000000000000000000000000000000000000",
      "working_tree_clean": true
    }
  },
  "declared": {
    "allowed_paths": [
      "docs/POST_RV2_03_WORKFLOW_OPTIMIZATION_CONTRACTS_V1.md"
    ]
  },
  "derived": {
    "starting_state_matches_declared": false,
    "reason": "example data only"
  },
  "sources": [
    {
      "kind": "command",
      "id": "git-status-example"
    }
  ],
  "invalidates_on": [
    "git_head_change",
    "working_tree_change",
    "github_read_change",
    "auth_change",
    "approval_change"
  ],
  "safety": {
    "contains_secrets": false,
    "manual_edits_allowed": false,
    "commit_as_current_truth_allowed": false
  }
}
```

## 6. Review Packet Contract

Review Packet evidence is organized into three levels.

Level 1 - Decision Summary: a concise reviewer-facing verdict, changed files, validation result, safety confirmation, and remaining blocker list.

Level 2 - Structured Review Packet: a machine-readable or consistently structured record containing task identity, governance references, command results, changed paths, diff summary, validation matrix, safety assertions, and links or paths to raw artifacts.

Level 3 - Raw Evidence Archive: complete command stdout/stderr artifacts, raw diffs, status output, hashes, and any read-only issue or file snapshots used to support the review.

Fail-closed conditions:

- Level 1 claims success but Level 2 is missing required validations
- Level 2 points to missing or unreadable Level 3 artifacts
- raw evidence contradicts the summary
- evidence omits required stdout or stderr artifacts
- changed files exceed the approved allowed scope
- command result records are missing exit codes or timeout state
- stale Current-State Manifest data is treated as current truth
- any safety assertion is unknown for a high-risk boundary

Review Packet compaction may reduce repeated prose, but raw evidence remains available.

## 7. Command Result Contract

Every recorded command must produce a Command Result record with:

- command id
- argv
- cwd
- start time
- end time
- exit code
- timed_out
- killed
- stdout artifact path
- stderr artifact path
- stdout byte count
- stderr byte count
- decoding notes
- hashes

Empty stdout and empty stderr must still produce evidence artifacts. Empty artifacts should have byte counts of `0` and hashes of the empty file content so reviewers can distinguish "empty" from "not captured."

The record must preserve argument vectors when possible. Shell string commands may be recorded only when the command was actually launched through a shell.

## 8. Generic Project Execution Gate V1 Scope

Generic Project Execution Gate V1 may cover:

- starting-state verification
- allowed-file verification
- test orchestration
- `git diff`
- `git diff --check`
- final git state
- compact JSON evidence generation

Generic Project Execution Gate V1 must not cover:

- semantic acceptance judgment
- commit, push, PR, or merge
- Issue mutation
- approval consumption
- live Bridge request publication
- Dispatcher, Runner, or Codex execution
- dependency or tool installation
- service, watcher, or MCP behavior

The gate may report facts and fail-closed states. It must not decide that a feature is acceptable, consume approval, or perform a no GitHub write boundary crossing. It must preserve no live Bridge authority unless a later separately approved Layer 3 harness owns that work.

## 9. Model Tiering

Model Tiering classifies work by risk and judgment required.

Tier 0 - deterministic script/tool: formatting, schema validation, JSON parsing, diff checks, command capture, and other deterministic tasks.

Tier 1 - low-risk semantic formatting: concise summaries, report reshaping, evidence packet compaction, and documentation cleanup that does not alter authority or technical meaning.

Tier 2 - bounded engineering execution: small to moderate implementation tasks with explicit allowed paths, tests, and no authority expansion.

Tier 3 - high-risk judgment and complex engineering: contract design, architecture boundary decisions, safety model changes, live workflow acceptance, broad refactors, or tasks with ambiguous product or authority impact.

Upgrade triggers:

- authority, side effects, or trust boundary could change
- current-truth sources conflict
- live Bridge, Dispatcher, Runner, Codex, GitHub write, approval, or install behavior is involved
- allowed paths or acceptance scope are ambiguous
- repeated repair indicates the task was under-classified

Downgrade conditions:

- task is deterministic and fully specified
- current state is captured by a fresh manifest
- edits are documentation-only or schema-only inside approved paths
- validations are mechanical and repeatable
- no semantic acceptance judgment is required

Stage-based composition is encouraged. For example, Tier 0 can collect evidence, Tier 1 can format it for review, Tier 2 can make a bounded patch, and Tier 3 can be reserved for the initial contract decision or final authority review.

## 10. Go / No-Go

Go when:

- repeated prompt and evidence work is reduced
- reviewer blockers do not increase
- raw evidence remains available
- contracts and safety boundaries remain explicit
- no high-risk authority is blurred

No-Go when:

- token savings increase repair count
- reviewer must reconstruct omitted context
- stale derived data is treated as current truth
- helper becomes a second platform
- tool modifies config unexpectedly
- semantic coverage weakens

No-Go states must fail closed and produce reviewable reasons rather than silently continuing.

## 11. OPT-02 Handoff

OPT-02 may later implement a Minimal Evidence Collector Prototype if separately approved.

OPT-02 may be bounded to:

- Python standard library only
- `begin`, `run`, and `finalize`
- docs and code profiles only
- no live profile
- no Git write
- no remote mutation
- facts only
- no acceptance decision

This document does not authorize OPT-02. It only defines the boundary that a later OPT-02 task packet should inherit if the user approves that implementation node.
