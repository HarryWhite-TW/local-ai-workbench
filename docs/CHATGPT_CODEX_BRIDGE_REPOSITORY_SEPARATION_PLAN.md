# ChatGPT-Codex Bridge Repository Separation Plan

## Decision Context

The ChatGPT-Codex bridge is intended to become reusable cross-project development infrastructure. `local-ai-workbench` is the first validated host and reference host, not the permanent repository boundary.

Roadmap v2 tracker #168 is canonical. RV2-00, RV2-01, and RV2-02 are `DONE`. RV2-03 is the current active node in Phase A on branch `rv2-03-phase-a-host-hardening`. The accepted RV2-01 smoke ran one successful B2/Dispatcher/Runner/Codex chain on clean `master` at `f41172b1ab25b2f4db4408f2fa825deb6e754cbb`, with manifest SHA-256 `34d17e23f94f939765b5ed761d34aa1b3ec018e31f868857431c02314e9bf080`. Evidence comments are dispatch `4795080463`, Inbox `4795082149`, Runner review bundle `4795131449`, and matching `LAWBRUNNER-RESULT` `4795131543`.

The smoke succeeded with Codex exit code `0`, no retry, no changed files, and a clean final worktree. It proves one supervised path, not daily B3 operational readiness. RV2-03 Phase A implementation evidence has progressed, repository documentation and canonical GitHub status synchronization are complete, and RV2-03 Phase A final acceptance passed on 2026-06-30. Phase B operational acceptance on the user-designated Primary Operational Host remains separately gated and required, RV2-03 is not `DONE`, and the experimental `feat/lawb-controlled-development-skill` branch is separate, unmerged, and not a mainline capability.

The current Primary Operational Host is the course Windows computer. The home Windows computer is a Secondary Compatibility Host. Because the course host may lose local operator state after reset, cross-reset duplicate suppression or fail-closed reconciliation remains a required and unproven RV2-03 acceptance condition.

## Current Coupling Inventory

The proven baseline currently couples generic bridge behavior and host assumptions inside `local-ai-workbench`:

- Python Bridge Operator modules under `src/local_runner_bridge/`;
- PowerShell Dispatcher, Runner, bootstrap, and related launch scripts;
- repository-local tests and documentation;
- fixed GitHub identity `HarryWhite-TW/local-ai-workbench`;
- default branch `master`;
- fixed Bridge Inbox Issue `#147`;
- repository-relative commands, allowed paths, timeouts, and result-write rules;
- local environment and state-path conventions;
- governance documents and Roadmap v2 evidence.

Before migration, implementation work must classify each dependency as generic bridge core, host adapter, host profile data, test fixture, or host-owned governance.

## Target Repository Boundary

The generic bridge core should contain protocol parsing, request validation, state binding, bounded operator control, Dispatcher/Runner orchestration contracts, result validation, local state handling, and safety enforcement that do not depend on one host repository.

Host-specific configuration should remain outside the generic core. It includes repository identity, local checkout root, branch policy, fixed Inbox, trusted actors, action and path allowlists, verification commands, timeouts, result-write policy, launch commands, and host governance references.

The target boundary must preserve ChatGPT as the primary interface, GitHub as the auditable request/result surface, manual `PollOnce` as recovery only, and all existing approval and no-high-risk-action boundaries.

## Host Profile Contract

Each host must provide an explicit, reviewable profile containing at least:

- local repository root;
- GitHub repository identity;
- default branch;
- fixed Inbox issue;
- trusted actors;
- allowed actions;
- allowed paths;
- verification commands;
- timeouts;
- result-write policy.

The contract should also carry a profile schema version, local state location, launcher commands, required governance-document paths, clean-worktree policy, result protocol versions, and whether each action is dry-run-only or write-capable.

Profiles are configuration, not approval. A profile must not enable an action beyond the generic core allowlist or bypass task-specific approval, branch/HEAD binding, expiry, clean-tree checks, trusted-author checks, or result validation.

## Known Operational Blockers And Migration Prerequisites

The following requirements are split by current evidence status. This is not a blanket complete claim.

Implemented or partially proven during RV2-03 Phase A:

- A0 Windows host compatibility hardening;
- A1 Host Check Harness;
- A2 request lifecycle and `CONSUMED` handling;
- A3 read-only publication preflight, including `current_request_count = 0` gating before publication and short execution TTL handling;
- B2 tool-resolution preflight;
- fresh-reboot branch recovery;
- course-computer environment recovery;
- post-recovery readiness gate;
- Recovery Script native-command/auth hardening;
- current request lifecycle telemetry sufficient for the implemented A2/A3 paths.

Still deferred to RV2-04 or Phase B where not fully proven:

- `manifest_review_expires` and `execution_request_expires` must be separate fields;
- a versioned Host Profile;
- the full shared Bootstrap/runtime resolver contract where still deferred;
- each versioned Host Profile must explicitly carry reviewed executable paths for `gh`/`gh.exe` and Codex;
- B1 and B2 must provide safe, stage-specific diagnostic information instead of only `github_read_unavailable` or a generic `RuntimeError`;
- Runner evidence must propagate consistently into the outer result, including `changed_files`, `review_id`, `diff_fingerprint`, and `files_fingerprint`, where still deferred;
- Phase B daily B3 operational acceptance on the user-designated Primary Operational Host, including state-loss safety when that host is ephemeral;
- startup, tray, service, and MCP remain separate future nodes.

RV2-03 owns operational acceptance on the user-designated Primary Operational Host, including cross-reset duplicate suppression or fail-closed reconciliation when local state can be lost. RV2-04 owns the versioned Host Profile, distinct expiry fields, any remaining shared resolver contract, diagnostic schema, and Runner-to-outer-result evidence contract not already proven by Phase A.

These requirements must be accepted before repository separation or cross-project portability may be considered operationally credible. Documentation of the target boundary alone is not evidence that the current bridge can be safely extracted or reused across hosts.

## Migration Stages

1. Inventory and classify current coupling without changing runtime behavior.
2. Define and validate a versioned host-profile schema using the current `local-ai-workbench` values.
3. Add characterization tests proving the existing in-repository baseline before boundary changes.
4. Introduce an internal profile-loading seam while retaining current paths and launchers.
5. Prepare a separate generic-core repository or package layout only under a separately approved migration implementation node.
6. Run compatibility tests against `local-ai-workbench` with identical request, safety, and result behavior.
7. Validate a second, materially different repository with its own profile.
8. Cut over only after both hosts pass acceptance and rollback rehearsal.

No stage may silently activate the next stage or consume approval for it.

## Compatibility And Rollback

The current in-repository implementation remains the proven baseline until migration acceptance passes. Migration must preserve protocol shapes, fail-closed behavior, one-request execution bounds, no-retry behavior, trusted-author validation, branch/HEAD binding, clean-worktree requirements, and result readback.

Compatibility evidence must compare old and candidate paths using the same bounded fixtures and expected outcomes. During migration, the host must retain a documented way to select the existing in-repository baseline. Rollback means restoring that selection without rewriting evidence, deleting state, or automatically cleaning repository changes.

## Acceptance Criteria

Repository separation may be called complete only when:

- generic core and host-specific configuration are explicitly separated;
- the host-profile schema contains all required fields and rejects missing or unsafe values;
- `local-ai-workbench` passes equivalent positive and fail-closed cases through the candidate boundary;
- at least one second repository with a different profile passes the same portability suite;
- at least two different repositories are validated before any cross-project portability claim;
- result packets and audit evidence remain ChatGPT-readable;
- no automatic commit, push, close, merge, label edit, approval chaining, retry, startup, tray, service, or MCP authority is introduced;
- rollback to the proven in-repository baseline is tested and documented;
- the migration implementation and cutover receive separate explicit approval.

## Explicit Non-Authorization

This plan is design only. It does not authorize:

- creation of a new repository;
- moving or deleting bridge files;
- package publishing;
- import, launcher, runtime-path, or profile rewiring;
- runtime-boundary changes;
- changing trusted actors, allowed actions, allowed paths, or result-write authority;
- automatic polling, startup, tray UX, service behavior, or MCP;
- automatic commit, push, Issue close, label edit, PR creation, merge, or approval chaining;
- activation of RV2-03 or any later node.

A later separately approved migration implementation node is required.
