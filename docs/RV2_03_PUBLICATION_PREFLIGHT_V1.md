# RV2-03 Publication Preflight v1

## Purpose

RV2-03 A3 adds a local, read-only publication preflight before Approval A
request comments are published.

The preflight does not publish GitHub comments, invoke B2, start the B3 loop,
invoke Dispatcher, invoke Runner, invoke Codex, stage, commit, or push.

## Protocol

```text
lawb.rv2_03_publication_preflight.v1
```

The protocol is review evidence only. It does not grant publication authority.

## Validation Order

1. Normalize one UTC evaluation timestamp.
2. Validate the existing B4-D manifest with that timestamp.
3. Stop before GitHub reads if manifest validation fails.
4. Enforce the RV2-03 A3 execution TTL.
5. Stop before GitHub reads if TTL validation fails.
6. Run local repository readiness before any possible publication-safe result.
7. Fail closed unless readiness confirms the exact repo root, branch, HEAD,
   clean tree, GitHub CLI availability, GitHub authentication, and repository
   read availability.
8. Resolve the existing B3 state directory without creating it.
9. Read `processed_requests.jsonl` if present.
10. Fail closed if processed history is malformed or unreadable.
11. Call existing B1 lifecycle classification with the same timestamp and
   consumed request IDs.
12. Allow Approval A preview only when publication is safe.

## TTL

The hard maximum remaining execution TTL is 20 minutes:

```text
MAX_EXECUTION_TTL_SECONDS = 1200
```

Publication preflight accepts only:

```text
0 < manifest_expires - evaluated_at_utc <= 1200 seconds
```

The comparison uses the actual timedelta seconds, including fractional seconds.
It does not truncate to an integer before validation, so a remaining TTL such as
`1200.000001` seconds blocks publication.

The historical four-hour B4-D manifest validator remains unchanged. A3 applies
the short TTL only in the publication-preflight layer.

Distinct `manifest_review_expires` and `execution_request_expires` fields remain
deferred to RV2-04.

## Publication-Safe Rule

Publication may be safe only when:

- manifest validation passes;
- TTL validation passes;
- local readiness passes for the exact repo root, manifest branch, manifest
  HEAD, clean working tree, GitHub CLI availability, GitHub authentication, and
  repository read availability;
- processed-history reading passes;
- B1 reports `result == blocked`;
- B1 reports exactly one blocked reason, which is one of:
  - `missing_request`;
  - `missing_current_request`;
  - `no_current_request_after_consumption`.
- B1 reports `current_request_count == 0`;
- B1 reports `fixed_inbox_read_performed is True`;
- B1 reports `github_read_available is True`;
- B1 repository and configured Inbox issue match the canonical A3 repository
  and Inbox.

Consumed and expired historical requests do not block publication.

One or more CURRENT requests block publication.

Any unexpected, partial, contradictory, or structurally inconsistent B1 result
fails closed.

## Output

The preflight output includes:

- protocol;
- result;
- publication safety;
- blocked reasons;
- evaluated UTC;
- max and remaining TTL;
- manifest hash and binding when available;
- Approval A preview only when safe;
- B1 telemetry including full request lifecycle;
- local readiness telemetry without raw command output;
- explicit safety evidence that no prohibited action occurred.

All CLI outcomes use the A3 protocol, including invalid CLI arguments, manifest
read failures, duplicate JSON keys, malformed JSON, blocked preflight results,
and internal preflight failures. CLI error payloads use structured safe error
codes and do not expose raw exception messages.

## Limitation

The preflight is a point-in-time read-only check. It does not atomically publish
the request comments. If publication is delayed, the preflight should be rerun.
