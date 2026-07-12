# WF-REENTRY Native Capability Overlap Review

Status: ACCEPTED CAPABILITY ADJUDICATION
Record: WF-REENTRY-SYNC
Scope: durable strategy judgment; not implementation authority or immutable platform truth

## Purpose and evidence boundary

This record re-enters the Workflow strategy after reviewing overlap among native Chat, Codex, and Work surfaces and the existing custom Bridge. It prevents the Workflow from being equated permanently with one GitHub-based transport path while preserving the governance and safety capabilities that remain valuable.

The evidence classes in this record are distinct:

- **Durable governance judgment:** authority, risk, current-truth, evidence, review, recovery, and durable-truth disciplines remain required regardless of transport or model provider.
- **Observed current product reality:** Chat, Work, and Codex are available as distinct integrated execution surfaces in the current ChatGPT product experience.
- **Reasonable engineering inference:** native routing may replace transport-only custom infrastructure where it demonstrates equivalent or better execution, evidence, recovery, and reviewability.
- **Unknown / not fully proven:** reliable full-result readback in this user's actual App environment is not fully proven because a completed task has appeared to finish while its final result remained inaccessible.

Current platform capabilities are mutable current truth and require future fresh verification. Specific current OpenAI UI behavior is not an immutable governance contract.

## Strategic repositioning

The Workflow is not identical to one transport path. Its preferred strategic role is the **Human-Governed AI Engineering Control Layer**.

The Workflow controls:

- who does the work;
- execution-surface selection;
- scope and authority;
- approval and risk delta;
- governance truth and observed current truth;
- evidence and review;
- recovery and durable truth.

It may govern multiple paths:

A. Chat direct answer
B. Chat -> Codex
C. Chat -> Work
D. specialized high-assurance Bridge path
E. manual relay fallback

Not every engineering task must use the custom GitHub Bridge.

## Capability adjudication

### KEEP: governance core

Engineering node, Acceptance contract, Risk package, Authority boundaries, Risk delta, Governance truth vs observed current truth, Evidence-first final review, Durable truth sync, Final reviewer adjudication, and Go / No-Go discipline are **KEEP**.

These capabilities remain valuable across transports and model providers. Stronger agents do not automatically supply task-specific authority, fresh current-truth discipline, semantic acceptance, recovery evidence, or durable project governance.

### KEEP + THIN: routing and review

Model / execution-surface routing is **KEEP + THIN**. Preserve role-based routing while reducing repeated routing prose.

The three-level review packet is **KEEP + THIN**. Keep Level 1 as a concise decision summary, inspect structured Level 2 evidence when needed, and preserve Level 3 raw evidence for conflict, high-risk review, or deep audit. Do not dump all raw evidence into every top-level response.

### THIN: repeated packet and transport ceremony

The Layered Task Packet is **THIN**. Stable governance should be referenced rather than repeatedly copied, current truth should be freshly verified, and execution packets should contain only the task-specific delta.

The Formal Current-State Manifest is **KEEP CONCEPT / THIN USAGE / CONDITIONAL**. Reserve a formal machine-readable manifest for work where it adds real value, including high-risk, long-running, auth-sensitive, multi-host, remote-mutation, stale-prone, or recovery-critical tasks.

GitHub Issue as universal transport, the custom Bridge's universal transport role, and the Dispatcher / Runner transport-only role are **THIN**. These concepts are not rejected; their transport ceremony should not be mandatory when a simpler path proves equivalent.

### Conditional capabilities

OPT-02 Minimal Evidence Collector is **THIN / CONDITIONAL**. It should not become mandatory ceremony for every small task.

OPT-06 Systematic Debugging Profile is **KEEP / CONDITIONAL DEFAULT** for ambiguous, safety-relevant, environment-sensitive, or evidence-heavy work, not trivial deterministic defects.

### Manual relay

Manual copy/paste is **FALLBACK ONLY**. It is not the final target workflow. It is currently used because native task handoff and result-readback UI has been unreliable for this user, including a real case where execution appeared complete but the final result was inaccessible. Manual relay remains the temporary reliable fallback and must not be presented as the desired end state.

### Native Chat, Codex, and Work

Native Chat -> Codex dispatch is a **REPLACE_BY_NATIVE CANDIDATE**, not an unconditional default. Native result readback is **NOT YET FULLY PROVEN IN THIS USER ENVIRONMENT**.

Native routing may replace transport-only custom infrastructure only where observed evidence demonstrates equivalent or better execution, full-result readback, raw evidence, recovery, and reviewability. Current native integration does not prove universal reliability, permanent product behavior, equivalent cross-reset duplicate safety, or equivalent durable reconciliation, and it does not already replace every Bridge capability.

### Dispatcher, Runner, and specialized Bridge value

The Dispatcher / Runner transport role is **THIN**. Their safety role is **KEEP SPECIALIZED**. The custom Bridge is a specialized high-assurance execution path, not universal mandatory transport.

Specialized value includes:

- branch and HEAD binding;
- clean-tree checks;
- one-request execution bounds;
- no automatic retry;
- trusted-author validation;
- fail-closed behavior;
- structured result validation;
- independent durable evidence;
- recovery;
- auditable request and result identity.

This adjudication neither declares all current Bridge code permanently required nor calls for its deletion.

### Durable reconciliation

Cross-reset duplicate suppression / durable reconciliation is **KEEP**. RV2-03 accepted evidence proved that a completed request did not rerun after complete local operator-state loss: trusted durable completion reconstructed consumed state, and the later duplicate gate prevented execution.

Native ChatGPT/Codex does not yet have a separately proven, user-verifiable equivalent cross-host reset and duplicate-suppression contract in this environment.

### DEFER

The existing bounded fixed-Inbox polling path governed by Bridge Operator v0 remains part of the current governed Bridge baseline and is not deauthorized by this record. Expanded or broader unattended polling beyond that fixed-Inbox contract is **DEFER**. Startup, tray, service, and MCP are **DEFER**. Physical repository separation is **DEFER**. RV2-04 automatic continuation is **NOT AUTHORIZED**.

These items are not cancelled forever and are not automatically next. Each requires new evidence and an explicit engineering node. Native overlap must be considered before further Bridge investment, and physical extraction must not begin merely because a separation plan exists.

### OPT-07

`codebase-memory` remains **NO-GO**. Its comparable exploration reduction was `13.04%`, below the required `30%` threshold, and it missed safety-critical relations. It is not adopted as a required or default exploration mechanism.

## Direction Lock status

Direction Lock v1.2 is:

- historically valid;
- still authoritative for existing Bridge work;
- its transport strategy is classified by WF-REENTRY as **REVIEW_REQUIRED** for future explicit change-control review.

The Direction Lock remains operative for current Bridge work until separately approved change control actually updates it. WF-REENTRY does not modify, override, revoke, supersede, or deactivate the Direction Lock. The Direction Lock was designed around an auditable custom ChatGPT -> GitHub -> Dispatcher/Runner/Codex -> GitHub -> ChatGPT path. Current native platform integration creates a genuine overlap question, but native readback and recovery equivalence is not proven in this user's real environment. The safe status is future review-required, not immediate replacement.

## Current classification

| Capability | Classification |
| --- | --- |
| Engineering node | KEEP |
| Acceptance contract | KEEP |
| Risk package | KEEP |
| Authority boundaries | KEEP |
| Risk delta | KEEP |
| Governance vs observed truth | KEEP |
| Evidence-first final review | KEEP |
| Durable truth sync | KEEP |
| Final reviewer adjudication | KEEP |
| Model/surface routing | KEEP + THIN |
| Layered task packets | THIN |
| Formal Current-State Manifest | THIN / CONDITIONAL |
| Three-level review packet | KEEP + THIN |
| Minimal Evidence Collector | THIN / CONDITIONAL |
| Systematic debugging profile | KEEP / CONDITIONAL DEFAULT |
| Manual copy/paste | FALLBACK ONLY |
| GitHub Issue as universal transport | THIN |
| Native Chat -> Codex dispatch | REPLACE_BY_NATIVE CANDIDATE |
| Native result readback | NOT YET FULLY PROVEN |
| Dispatcher/Runner transport role | THIN |
| Dispatcher/Runner safety role | KEEP SPECIALIZED |
| Durable reconciliation / duplicate suppression | KEEP |
| Expanded/unattended polling beyond existing bounded fixed-Inbox baseline | DEFER |
| Startup / tray / service / MCP | DEFER |
| Physical repository separation | DEFER |
| codebase-memory | NO-GO |

## Recommended next review

Current Roadmap v2 governance requires explicit consideration of `RV2-P1` after RV2-03. The **Native-vs-Bridge Reliability Benchmark** is a recommended evidence input, sub-review, or candidate review within or after that explicit RV2-P1 consideration. It must not become an alternate next-step queue that bypasses RV2-P1.

Possible comparison dimensions are task-dispatch friction, execution reliability, full-result readback, raw-evidence availability, reviewer reconstruction cost, failure and interruption recovery, durable identity, duplicate suppression, cross-reset behavior, authority boundaries, user interaction burden, and quota/token/time cost.

Neither RV2-P1 nor the benchmark is activated by this record. The benchmark requires explicit engineering-node approval and this record does not create an implementation task, activate RV2-04 or Phase 5.4, begin repository separation, start Gateway implementation, or authorize any other implementation node.
