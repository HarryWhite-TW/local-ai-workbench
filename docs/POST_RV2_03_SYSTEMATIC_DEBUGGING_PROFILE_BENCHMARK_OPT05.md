# OPT-05 LAWB Systematic Debugging Profile Benchmark

## Purpose

OPT-05 evaluates whether a systematic debugging profile should be used for later Local Document-to-Knowledge Workbench project work.

The benchmark asks whether a fixed profile can reduce chaotic investigation, make blockers easier to classify, separate symptom, current truth, hypothesis, evidence, fix, and verification, reduce false blockers without hiding real risk, and preserve reviewer judgment plus user approval boundaries.

This benchmark does not authorize source code changes, test changes, script changes, Git writes, GitHub writes, Issue mutation, live Bridge execution, Dispatcher, Runner, Codex runtime task execution, dependency installation, tool installation, service, watcher, MCP, RV2-04, or OPT-06.

## Method

The method is a qualitative workflow benchmark:

- define a systematic debugging profile as an example-only JSON contract
- compare it against four recent pain cases from repository work
- evaluate whether the profile would have improved investigation order, blocker classification, evidence gathering, and final review clarity
- validate the profile and metrics JSON with `json.tool`
- capture validation evidence with the Minimal Evidence Collector using process-local `PYTHONPATH=src`

This benchmark does not fix any defect, modify runtime behavior, alter tests, write scripts, touch GitHub Issues or PRs, or implement a debugging tool.

## Debugging Profile Workflow

The proposed debugging workflow is:

1. Capture the symptom in plain terms.
2. Revalidate current truth before diagnosis.
3. Check scope and authority boundaries.
4. Reproduce the issue or identify the evidence gap.
5. List plausible hypotheses without choosing too early.
6. Select the most likely root cause based on evidence.
7. Plan one focused repair only if repair is authorized.
8. Verify with the narrowest relevant commands.
9. Prepare a final reviewer packet with evidence, residual risk, and safety confirmation.
10. Stop or escalate when the issue needs approval, a second repair, a scope delta, or a different execution context.

The profile is intended to slow down the moment where a symptom is mistaken for a cause. It should make blockers more legible without converting uncertainty into false certainty.

## Historical Pain Points From Recent Work

Recent workflow pain points include:

- host restore and course-computer readiness checks that produced false blocker risk
- RV2-03 manifest and input recovery where stale or missing context could have been mistaken for current truth
- OPT-02 denylist review where a subtle safety blocker required a second focused repair
- OPT-04 and other untracked-file reviews where normal `git diff` did not show raw content
- command-context mismatches, such as local `PYTHONPATH=src` being acceptable while permanent config changes remained forbidden
- evidence spread across terminal output, docs, raw diffs, JSON artifacts, and final summaries

## Benchmark Cases

### Case A - Course Host Restore False Blockers

Manual debugging risk:

- environment symptoms could be mistaken for repository defects
- host readiness and bootstrap readiness could be conflated
- execution context could produce false blockers

Profile-assisted comparison:

- `current_truth_gate` separates host state, repo state, and task packet declarations
- `blocker_taxonomy` can classify environment blockers and execution-context mismatches before source repair is considered
- `stop_or_escalate` prevents silent host repair or unauthorized config changes

Result: improved blocker classification; unchanged need for human judgment on host readiness.

### Case B - RV2-03 Manifest / Input Recovery

Manual debugging risk:

- stale generated artifacts could be treated as durable truth
- missing manifest inputs could trigger speculative recovery
- acceptance evidence could be mixed with implementation authority

Profile-assisted comparison:

- `current_truth_gate` requires direct source-of-truth reads before diagnosis
- `evidence_requirements` call out missing or stale artifacts as evidence gaps
- `scope_boundary_check` keeps live Bridge and GitHub write authority separate from local diagnosis

Result: improved current-truth discipline; unchanged need for reviewer acceptance.

### Case C - OPT-02 Denylist Blocker And Second Repair

Manual debugging risk:

- a passing smoke could obscure a semantic safety issue
- the first repair could be overgeneralized
- second repair required explicit approval

Profile-assisted comparison:

- `hypothesis_list` preserves alternate causes before choosing a fix
- `root_cause_selection` distinguishes test coverage gaps from source contract blockers
- `repair_budget_rules` make second-repair approval explicit

Result: improved risk visibility; unchanged need for code review and approval for additional repair.

### Case D - OPT-04 Raw Evidence Review Of Untracked Files

Manual debugging risk:

- normal `git diff` omits untracked file content
- reviewer may not receive raw content needed for approval
- final status can look correct while evidence is incomplete

Profile-assisted comparison:

- `evidence_requirements` identify raw no-index diff as required when files are untracked
- `final_reviewer_packet` separates status from raw content evidence
- `stop_or_escalate` classifies missing raw evidence as an evidence gap, not as a source defect

Result: improved evidence completeness; unchanged need for raw reviewer inspection.

## What The Profile Improves

The profile appears to improve:

- investigation order
- blocker classification
- separation of symptom from cause
- separation of current truth from stale artifacts
- repair-budget discipline
- evidence completeness
- final reviewer packet clarity
- preservation of approval boundaries

## What The Profile Does Not Solve

The profile does not solve:

- defects by itself
- missing source authority
- invalid task scope
- absent user approval
- missing tools or environment capabilities
- semantic acceptance
- raw diff review
- code safety review
- live Bridge or GitHub write acceptance

It is not a debugging tool, not a runtime component, and not an approval mechanism.

## Reviewer Acceptance Checklist

A reviewer can accept this benchmark if:

- the report states the no-authority boundary clearly
- the profile JSON is valid and marks itself `example_only: true`
- the profile does not pretend to be current repo truth
- the profile separates symptom, current truth, hypothesis, evidence, fix, and verification
- blocker taxonomy includes environment, source contract, test coverage, evidence, execution context, approval, scope delta, and second-repair blockers
- repair budget rules require stopping or approval when a second repair is needed
- user approval boundaries remain explicit
- metrics use qualitative ratings only
- OPT-06 is only a handoff suggestion and is not implemented

## Risk Boundaries

Known risks:

- process overhead if the profile is applied to tiny obvious defects
- false confidence if taxonomy labels are treated as proof
- delay if current-truth gates become rote ceremony
- hidden authority expansion if the profile is treated as permission to repair
- reviewer fatigue if final packets become too verbose

Mitigations:

- use the profile when debugging is ambiguous, safety-relevant, or evidence-heavy
- keep repair budgets task-specific
- keep raw evidence available
- preserve reviewer judgment
- stop when approval, scope delta, second repair, live execution, GitHub write, or source change authority is missing

## Go / No-Go

Go to one bounded follow-up planning node only.

The profile should be used for later nodes when debugging has meaningful ambiguity, environment risk, safety boundaries, or reviewer evidence burden. It should not be mandatory for trivial deterministic checks.

No-Go if the profile is used to bypass reviewer judgment, skip current-source reads, justify unauthorized repairs, or turn qualitative classification into semantic acceptance.

## OPT-06 Handoff

Recommended next node:

```text
OPT-06 - Systematic Debugging Profile Follow-Up Planning
```

Small OPT-06 boundary, if separately approved:

- choose one recent or synthetic debugging scenario
- apply the profile read-only
- compare reviewer packet clarity against the prior workflow
- do not implement a debugging tool
- do not modify source, tests, scripts, config, GitHub Issues, or PRs
- preserve no GitHub write, no live Bridge, no Dispatcher, no Runner, no Codex runtime task execution, no RV2-04, no service, no watcher, no MCP, and no dependency installation

OPT-06 is not authorized by this benchmark.
