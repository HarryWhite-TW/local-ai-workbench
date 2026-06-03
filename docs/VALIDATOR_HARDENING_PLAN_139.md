# Validator Hardening Plan 139

## Purpose

This document defines #139 Validator Hardening Plan.

The purpose is to plan the next small hardening slice after the #138 read-only validator implementation.

This is a lightweight plan only.

This is not implementation.

This document does not modify validator code.

This document does not modify tests.

This document does not create scripts.

This document does not execute a runner or dispatcher.

This document does not execute Codex-side action.

This document does not write a Result Packet.

This document does not authorize commit or push.

## Current #138 baseline

#138 added the first read-only local runner bridge validation helpers:

```text
src/local_runner_bridge/__init__.py
src/local_runner_bridge/task_surface_resolver.py
src/local_runner_bridge/task_packet_validator.py
tests/local_runner_bridge/test_task_packet_validator.py
```

The current baseline includes `extract_task_packet`.

The current baseline includes `validate_task_packet`.

The current baseline includes targeted validator tests.

The validator parses explicit local text and returns local summary dictionaries.

The validator does not use the GitHub API.

The validator does not write files.

The validator does not write a Result Packet.

The validator does not execute Codex-side action.

The validator does not commit.

The validator does not push.

## Must fix next

The next implementation slice should harden the current parser and validator in the smallest useful way.

Must-fix items:

1. Reject unknown top-level fields.
2. Validate list-shaped fields for `allowed_files` and `forbidden_operations`.
3. Use stricter line-based boundary marker detection.

Rejecting unknown top-level fields keeps Task Packet v1 narrow and prevents accidental extra authority from being smuggled into accepted packets.

Validating `allowed_files` and `forbidden_operations` as lists keeps the current structural checks honest instead of accepting scalar placeholders.

Stricter line-based boundary marker detection prevents substring matches from being treated as valid packet boundaries.

## Should fix later

Later hardening can be useful, but it should not be bundled into the minimal next implementation slice.

Should-fix-later items:

1. Evaluate whether a fuller YAML parser is appropriate for this localhost prototype.
2. Add richer error codes for specific malformed packet shapes.
3. Add stricter value validation for `action_type` and `risk_level`.

These items can improve clarity and precision, but they have more design surface than the next small validator hardening pass needs.

## Explicitly not now

#139 does not authorize broader automation or writeback behavior.

Explicitly not now:

1. No GitHub fetch/write.
2. No Result Packet write.
3. No Codex-side action.
4. No full runner.
5. No dispatcher.
6. No always-on watcher.
7. No Lv5 / full automation.

The validator should remain a local, read-only evidence tool.

Validation success must not become execution approval, commit approval, push approval, or writeback approval.

## Minimal next slice proposal

The proposed next slice is:

```text
#140 validator hardening implementation slice
```

#140 should implement only the three `must_fix_next` items:

1. Reject unknown top-level fields.
2. Validate list-shaped fields for `allowed_files` and `forbidden_operations`.
3. Use stricter line-based boundary marker detection.

#140 should not introduce runner behavior.

#140 should not introduce dispatcher behavior.

#140 should not introduce GitHub API behavior.

#140 should not write Task Packets or Result Packets.

#140 should keep tests targeted to the validator and resolver behavior.

## Completion criteria

#139 is complete when this document defines:

1. Purpose.
2. Current #138 baseline.
3. Must fix next.
4. Should fix later.
5. Explicitly not now.
6. Minimal next slice proposal.
7. Completion criteria.
8. Current status.

#139 is not complete if it modifies validator code.

#139 is not complete if it modifies tests.

#139 is not complete if it creates scripts.

#139 is not complete if it modifies dependency files, `pyproject.toml`, `README.md`, or implementation docs outside this plan.

#139 is not complete if it writes a Result Packet.

#139 is not complete if it executes Codex-side action.

#139 is not complete if it creates a commit or push.

## Current status

Validator Hardening Plan 139 is defined as a docs-only planning artifact.

The current status is `reviewbundle_plan_only`.

Implementation is not authorized in #139.

The recommended next action is ChatGPT review, followed by a commit approval decision if the plan is accepted.
