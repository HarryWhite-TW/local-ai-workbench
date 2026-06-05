# Phase 3 Live Fetch Probe Decision Note (#154)

## 1. Purpose

This note summarizes Phase 3 live fetch probe evidence from #149 through #153 and records the next bounded decision.

The purpose is to decide whether to keep retrying historical GitHub comments or move to a controlled valid Task Surface live fetch smoke.

## 2. Issue Classification

```yaml
issue_number: 154
issue_role: support
risk_lane: fast
alignment: core_support
value_target: summarize the Phase 3 live fetch probe evidence from #149 through #153, conclude that authenticated explicit live fetch reaches validation dry-run, and decide that the next step should use a controlled valid Task Surface instead of retrying old comments
```

## 3. Phase 3 Direction Lock

The project target remains:

```text
ChatGPT -> explicit auditable task surface -> local read-only fetch -> validation dry-run -> JSON readback -> ChatGPT review -> user approval
```

Manual copy/paste remains fallback only, not the target workflow.

## 4. Evidence Summary: #149

#149 used exactly one explicit comment reference without a token.

The CLI accepted the explicit comment URL and printed bounded JSON, but the live read failed before validation dry-run with blocked HTTPError evidence.

Safety signals remained read-only:

- no broad scan
- no next/latest issue inference
- no GitHub writeback
- no Result Packet write
- no Codex-side action execution

## 5. Evidence Summary: #150

#150 used process-level `GITHUB_TOKEN`.

The authenticated smoke performed live fetch, used exactly one explicit comment reference, printed JSON to stdout, reached validation dry-run, and recorded a blocked validation result.

The blocked validation result showed that the selected comment body was not a valid Task Surface.

## 6. Evidence Summary: #151

#151 retried one separately approved explicit comment reference.

The authenticated smoke again performed bounded live fetch, printed JSON to stdout, reached validation dry-run, and recorded blocked validation.

No broad issue scan, alternate reference, or writeback was performed.

## 7. Evidence Summary: #152

#152 recorded the course-machine environment setup runbook.

It did not perform live fetch. It documented repeatable setup for process-level `GITHUB_TOKEN`, Codex process visibility, local Git author identity, repository sync checks, and safe shutdown checks on reset-card / restore-card course machines.

## 8. Evidence Summary: #153

#153 retried one separately approved explicit comment reference.

The authenticated smoke again performed bounded live fetch, printed JSON to stdout, reached validation dry-run, and recorded blocked validation.

The selected historical comment still did not validate as a valid Task Surface.

## 9. What Has Been Proven

The Phase 3 live fetch path has been proven at the boundary level:

- explicit single comment reference
- authenticated fetch
- stdout JSON
- validation dry-run reached
- no broad scan
- no writeback

The problem is no longer token setup, GitHub access, or CLI reachability.

## 10. What Has Not Been Proven

Existing tried comments did not prove valid Task Surface success because their validation result was blocked.

The probes have not yet proven:

- validation success on a fetched GitHub comment
- a controlled minimal valid Task Surface over live fetch
- any GitHub writeback
- any Result Packet write
- any runner, dispatcher, watcher, or autonomous behavior

## 11. Decision

Stop retrying old comments blindly.

The likely current blocker is that the selected historical comments are not valid Task Surface comments. Retrying more historical comments without controlling the content would test comment selection, not the live fetch and validation path.

## 12. Next Candidate Step

The next candidate issue should be:

```text
#155 Controlled Valid Task Surface Live Fetch Smoke
```

#155 should use one explicitly approved GitHub comment containing a deliberately minimal valid Task Surface.

Suggested #155 step:

```text
Create or select one controlled GitHub issue comment that intentionally contains a minimal valid Task Surface / Task Packet, then run the existing #146 CLI against exactly that one explicit comment URL to prove live fetch -> validation dry-run -> validation success.
```

This note does not implement #155, create a controlled comment, or write any GitHub comment.

## 13. Still Forbidden Behaviors

#155 must still avoid:

- GitHub writeback
- Result Packet write
- Codex-side action execution
- runner
- dispatcher
- watcher
- broad issue scan
- next/latest issue inference
- issue close
- label change
- PR / merge

These behaviors remain outside the proven boundary and require separate explicit approval if ever considered.

## 14. Final Boundary Statement

This decision note is docs-only. It records that authenticated explicit live fetch reaches validation dry-run, while valid Task Surface success remains unproven because the tried historical comments blocked validation.

The bounded next step is #155: a controlled valid Task Surface live fetch smoke using exactly one explicitly approved comment URL.
