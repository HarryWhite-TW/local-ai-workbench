# OPT-07 codebase-memory CLI-Only Benchmark

## Status

`DONE / NO-GO`

OPT-07 was an isolated, temporary benchmark of `DeusData/codebase-memory-mcp` v0.9.0 against the Local AI Workbench repository. The benchmark was accepted as a valid experiment, but adoption was rejected for the current workflow.

This record does not authorize installation, MCP integration, Codex or VS Code configuration, persistent indexing, watchers, services, PATH changes, dependency installation, repository modification, GitHub mutation, RV2-04, Issue #188 activation, or any later node.

## Benchmark Goal

Determine whether a temporary structural code graph could reduce repository exploration cost while preserving source-verified correctness, safety boundaries, and complete rollback.

The graph was never treated as current-truth authority. Safety-sensitive conclusions still required source, tests, and Git-state verification.

## Execution Boundary

The benchmark used:

- official `codebase-memory-mcp` release `v0.9.0`
- archive `codebase-memory-mcp-windows-amd64.zip`
- exact SHA-256 `92f96896f952e539f0d6cb34d7892a25064b677ccbf808b8f8310ad897e86f2c`
- official checksum match: `PASS`
- temporary benchmark root only
- temporary clone pinned to canonical `master@c1b28d408bd161aaee79a1c9f2644ab537d248c6`
- process-local cache and home/config environment overrides
- auto-index/watch disabled
- one explicit CLI index
- no installer
- no repository artifact
- no persistent process

The first raw-JSON index-worker invocation exited `1` with an empty worker log. The single allowed focused repair switched to the official CLI flags:

```text
codebase-memory-mcp.exe cli index_repository --repo-path <temp-repo> --mode fast --persistence false
```

That invocation succeeded with:

- exit code `0`
- `2,410` nodes
- `10,146` edges
- database size `11,796,480` bytes
- index elapsed time `1,109 ms`

## Fixed Benchmark Questions

Both variants used the same ten questions:

1. What are the main Bridge entry points?
2. Which functions invoke the Dispatcher?
3. Which tests directly cover durable reconciliation?
4. What calls the processed-request writer?
5. Which modules import the durable evidence resolver?
6. What functions can set `current_delegation_outcome`?
7. Which files participate in B3 request delegation?
8. What is the call path from Bridge Operator to Runner?
9. Which tests cover duplicate suppression?
10. What modules are affected by changing the processed-request record format?

## Variant A — Baseline Source Exploration

Baseline exploration used normal repository search and targeted source reads only.

Metrics:

- search operations: `11`
- source-read operations: `12`
- unique source files: `8`
- comparable exploration operations: `23`
- timed core phases: `1,111 ms`
- later corrections: none

The baseline produced source-verified answers for all ten questions.

## Variant B — Graph-Assisted Exploration

Graph-assisted exploration used the temporary code graph first, followed by mandatory source verification.

Metrics:

- graph calls: `10`
- source-verification reads: `10`
- comparable exploration operations: `20`
- graph/query plus source timed phases: approximately `1,126 ms`
- answer quality after source verification: `10/10 = 100%`
- safety-critical false positives: `0`
- safety-critical false negatives: at least `3` categories

The graph helped locate some direct tests, processed-request writers, duplicate-suppression tests, and selected symbols, but it did not provide sufficient safety-critical path completeness.

## Source-Verification Corrections

Source verification corrected or completed graph output in these important areas:

1. The graph trace omitted `_delegate_b3_request -> resolve_durable_completion`.
2. The graph trace omitted `_delegate_b3_request -> default_dispatcher_invoker/build_dispatcher_command`.
3. The graph did not represent `local_dispatcher_v1.ps1 -> Invoke-ReviewBundle -> local_runner_v1.ps1`.
4. An `IMPORTS` query returned zero rows even though source inspection proved real durable-evidence imports.

The benchmark observed no fabricated safety-critical relation, but the false negatives were sufficient to trigger the approved NO-GO condition.

## Exploration-Cost Calculation

Primary metric:

```text
exploration operations = search or graph calls + targeted source reads
```

Calculation:

```text
(23 - 20) / 23 * 100 = 13.04%
```

Required threshold:

```text
>= 30%
```

Result:

```text
FAIL
```

The graph-assisted path also did not improve timed core-phase duration: approximately `1,126 ms` versus the baseline `1,111 ms`.

## Stale-State Test

The stale-state test was not executed.

Reason: the graph had already missed safety-critical Dispatcher/Runner and durable-reconciliation relations. The approved benchmark contract required immediate NO-GO classification after such a failure, so further temporary source mutation was intentionally skipped rather than mechanically completing the remaining checklist.

## Rollback And Cleanup

Cleanup passed:

- temporary clone clean before deletion
- `.codebase-memory` repository artifact: none
- remaining codebase-memory processes: `0`
- temporary binary deleted
- archive deleted
- checksums deleted
- cache/database deleted
- temporary evidence deleted
- temporary clone deleted
- temporary root removed
- Codex/MCP/VS Code configuration changes: none
- daily repository remained clean and unchanged

Daily repository state observed at benchmark end:

- branch `rec-02-course-host-complete-recovery-v2`
- HEAD `7c3dbf3a6f73480e6ce6fcf65ec2ec5ebd52e415`
- worktree clean
- staged empty
- untracked none

This local state was not canonical current truth for the remote repository; the benchmark temporary clone used canonical `master@c1b28d408bd161aaee79a1c9f2644ab537d248c6`.

## Final Adjudication

`ACCEPTED AS NO-GO`

The benchmark itself succeeded as a bounded experiment. Tool adoption failed because:

- exploration-cost reduction was only `13.04%`, below the `30%` threshold
- safety-critical Dispatcher/Runner paths were incomplete
- durable reconciliation/import edges were incomplete
- source-verification and maintenance burden outweighed the observed exploration savings

Therefore `codebase-memory-mcp` is not adopted as a required or default Local AI Workbench exploration tool.

It may still have limited value for generic symbol discovery or selected non-critical navigation, but it must not be used as primary authority for cross-language Bridge, Dispatcher, Runner, duplicate-suppression, durable-reconciliation, or other safety-sensitive review.

## Model And Quota Observation

The user selected `GPT-5.6 Sol` with high reasoning for the task and observed approximately `18%` quota usage. The execution report exposed an internal `GPT-5` label and did not provide a verifiable reasoning-setting value. Therefore the exact serving model remains unverified; the `18%` figure is retained only as user-observed task-cost evidence, not as a precise model-pricing claim.

## Preserved Boundaries

OPT-07 completion does not activate:

- RV2-04
- Issue #188
- another OPT node
- MCP integration
- a watcher or background service
- repository-wide code graph adoption
- any automatic commit, push, PR, merge, or Issue mutation

No next node is automatically authorized by this record.
