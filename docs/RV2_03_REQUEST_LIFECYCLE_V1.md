# RV2-03 Request Lifecycle v1

## Purpose And Boundary

RV2-03 Phase A2 adds explicit Bridge Inbox request lifecycle classification for
Bridge Operator B1 and B3. Its purpose is to let a successfully processed
request stop counting as a current request immediately, even when its original
expiry time has not arrived.

This does not add request publication, live execution, retry, startup behavior,
trusted actors, action allowlists, or any commit, push, PR, label, merge, or
Issue-close authority.

## Lifecycle States

Each trusted, syntactically valid, identity-valid Inbox request marker is
classified as one of:

- `CURRENT`: valid and unexpired, and not already processed.
- `CONSUMED`: valid and already present in B3 processed-request history.
- `EXPIRED`: valid but past its expiry time.

Classification precedence is:

1. Validate marker trust, syntax, required fields, and identity.
2. If `request_id` is in B3 processed history, classify as `CONSUMED`.
3. Otherwise, if `expires` is at or before evaluated UTC, classify as `EXPIRED`.
4. Otherwise, classify as `CURRENT`.

A consumed request remains `CONSUMED` even after it later expires. Expiry stays a
fail-safe invalidation boundary; it is not the successful-completion lock
lifetime.

## Component Ownership

B1 receives consumed request IDs as an explicit optional input. B1 remains
read-only and does not read local B3 state files.

B3 owns processed-history integration. Before each B1 evaluation cycle, B3 reads
`processed_requests.jsonl` from its existing external state directory and passes
the IDs into B1. After one trusted matching successful Dispatcher result is
verified, B3 appends one processed record with `lifecycle_state=CONSUMED`.

Processed records remain append-only. A malformed processed history file fails
closed before Dispatcher invocation.

The accepted legacy processed-record shape is one JSON object per nonblank
JSONL line with:

- `protocol` exactly `lawb.bridge_operator_b3_processed_request.v1`;
- `request_id` as a string matching
  `^[A-Za-z0-9][A-Za-z0-9._:\-]{2,127}$`;
- no `lifecycle_state` field;
- the processed request identity fields:
  `target_issue`, `target_dispatch_request_id`, `requested_action`,
  `expected_branch`, and `expected_head`.

The accepted current processed-record shape uses the same protocol and
`request_id` and identity requirements, plus `lifecycle_state=CONSUMED`. When
`dispatcher_invoked` or `result_verified` exists, each must be exactly `true`.

Processed-history reading fails closed for malformed JSON, duplicate JSON keys,
non-object records, wrong protocol, non-string or grammar-invalid request IDs,
duplicate request IDs, unknown lifecycle states, missing or malformed identity
fields, and explicitly false verification fields. B3 and the publication
preflight use the same strict processed-history reader. Existing state is not
deleted, migrated, repaired, or rewritten by this validation.

A processed record consumes an Inbox marker only when both `request_id` and the
processed identity fields match the current marker. If `request_id` matches but
any identity field differs, B1 fails closed with
`processed_request_identity_mismatch`; B3 must not invoke Dispatcher, and the
publication preflight must not treat the result as a safe wait.

B3 summary lifecycle fields describe the latest B1 evaluation cycle. B3 request
identity fields describe the last request selected during the current B3 run. A
later consumed-only cycle clears current-selection lifecycle fields, but does not
erase the identity of a request already selected and processed in that same run.
A cold-start consumed-only run has no last selected identity.

## Selection Behavior

Only `CURRENT` requests count toward `current_request_count`.

One `CURRENT` request may be selected. More than one `CURRENT` request fails
closed as `multiple_current_requests`. `CONSUMED` and `EXPIRED` markers do not
contribute to that ambiguity.

If no `CURRENT` request exists but at least one valid marker is `CONSUMED`, B1
returns `no_current_request_after_consumption`. B3 treats only that specific
reason, plus the existing no-marker wait case, as a safe waiting condition.

Malformed, untrusted, ambiguous, or identity-invalid inputs fail closed before
lifecycle classification can make them non-blocking.

## Deferred Scope

The following remain deferred: publication gating on `current_request_count`,
short execution TTLs, manifest review expiry, execution request expiry, Host
Profile, bootstrap manifest, shared executable resolution, B2 executable
preflight, diagnostics schema redesign, Runner result evidence propagation, Git
author preflight, unstage recovery, stale-lock redesign, trusted-actor changes,
action allowlist changes, Codex or GitHub CLI version changes, live B3,
PollOnce, Dispatcher, Runner, background service, automatic retry, stage,
commit, push, PR, merge, labels, milestones, and GitHub Issue writes.
