# OPT-03 Historical A/B Benchmark

## 1. Purpose

OPT-03 evaluates whether the Minimal Evidence Collector should continue as the foundation for later workflow optimization after OPT-01 and OPT-02.

This Historical A/B Benchmark compares the manual workflow used in recent repository work with a collector-assisted local smoke. It asks whether the collector reduces repeated evidence work, reduces prompt and report bulk, makes reviewer evidence easier to locate, preserves raw evidence, avoids weakening safety boundaries, and avoids merely moving complexity elsewhere.

This benchmark does not authorize source code changes, test changes, Git writes, GitHub writes, Issue mutation, live Bridge execution, Dispatcher, Runner, Codex runtime task execution, dependency installation, tool installation, service, watcher, MCP, RV2-04, or OPT-04 implementation.

## 2. Method

The method is a historical A/B comparison:

- manual workflow baseline: recent Course environment restore, RV2-03 final acceptance, and OPT-02 implementation review evidence patterns
- collector-assisted local smoke: one Minimal Evidence Collector session with two read-only/local validation commands
- qualitative metrics: ratings of improved, unchanged, worse, or unknown
- limitations: no broad timing study, no precise token percentage claim, no live Bridge or GitHub write path, and no semantic acceptance judgment

The collector-assisted run used process-local `PYTHONPATH=src` for this repository's `src` layout. That setting was scoped to the shell process and did not modify permanent config or PATH.

Collector smoke evidence:

- evidence root: `C:\Users\admin\AppData\Local\Temp\opt03_ab_benchmark_evidence`
- session path: `C:\Users\admin\AppData\Local\Temp\opt03_ab_benchmark_evidence\session.json`
- review packet path: `C:\Users\admin\AppData\Local\Temp\opt03_ab_benchmark_evidence\review_packet.json`
- result: `success`
- command count: `2`
- failed command count: `0`
- artifact examples: `commands\001-opt01-json-validate\stdout.txt`, `commands\001-opt01-json-validate\stderr.txt`, `commands\002-opt02-tests\stdout.txt`, `commands\002-opt02-tests\stderr.txt`

## 3. Cases

### Case A - Course Environment Restore / Host Readiness

Manual pain observed:

- long repeated starting-state checks
- tool path confusion
- Host Check versus bootstrap READY distinction
- false blocker from execution-context mismatch
- large terminal evidence

Collector-assisted comparison:

- command results and artifacts can be grouped in one session and one review packet
- stdout and stderr paths make raw output easier to locate
- empty stderr still receives an artifact and hash, which reduces ambiguity
- the collector does not decide whether Host Check findings are acceptable

Case A result: improved evidence locality and raw evidence retention; unchanged need for human interpretation of host readiness layers.

### Case B - RV2-03 Final Acceptance

Manual pain observed:

- Host readiness blocker needed multiple follow-ups
- sandbox GitHub or Codex context produced false blocker risk
- final manifest/input source had to be traced
- preflight JSON needed raw review

Collector-assisted comparison:

- read-only command output can be captured in command result records
- failed command records would make exit code, stdout, stderr, timing, and artifact paths explicit
- compact summaries reduce transcript bulk while preserving raw evidence
- the collector does not distinguish true acceptance blockers from environment limitations by itself

Case B result: improved packaging of command evidence; unchanged need for reviewer judgment and source-of-truth review.

### Case C - OPT-02 Implementation Review

Manual pain observed:

- untracked files did not show in normal `git diff`
- raw diff retrieval required extra follow-up
- tests and CLI smoke evidence were separate from code review
- denylist blocker required focused repair

Collector-assisted comparison:

- test and JSON validation outputs can be grouped in one review packet
- command result records preserve exact argv, cwd, exit code, and artifact paths
- raw diff review for untracked files still needs explicit `git diff --no-index`
- code safety issues, such as denylist semantics, still require reviewer attention and focused repair

Case C result: improved validation packaging; unchanged need for raw diff evidence and code-level safety review.

## 4. Results

The collector improves command evidence packaging and raw artifact locality, but it does not replace reviewer judgment, semantic contract review, raw diff review, risk delta decisions, or high-risk approval gates.

Observed improvements:

- validation commands are collected under one evidence root
- stdout and stderr artifacts are stable paths rather than copied terminal fragments
- command records preserve argv, cwd, exit code, timing, byte counts, and hashes
- compact review packet summaries reduce repeated report material
- safety flags make non-authority explicit

Observed non-improvements:

- semantic acceptance still belongs to the reviewer
- untracked-file raw diff evidence still requires explicit no-index handling
- source safety still requires review, as shown by the OPT-02 denylist repair
- environment or auth failures can still require human classification
- the collector is not a sandbox

## 5. Go / No-Go

Go to one small next benchmark only.

The recommended next step is OPT-04, bounded to a UI Mockup-First Small Benchmark. OPT-04 should remain documentation/benchmark scoped unless separately approved otherwise.

Do not expand to live Bridge or GitHub write. The next step must preserve no GitHub write and no live Bridge authority. Do not treat collector success as task acceptance. Do not use this benchmark to authorize RV2-04, Dispatcher, Runner, Codex runtime tasks, watcher behavior, service behavior, MCP, commit, push, PR, or Issue mutation.

## 6. Risks

Known risks:

- false confidence from compact summaries
- stale evidence if a session is reused after Git, auth, approval, or working-tree changes
- denylist limitations, because the prototype denylist is a safety belt and not a complete sandbox
- `src`-layout `PYTHONPATH=src` requirement for local CLI module execution
- untracked-file raw diff still needs explicit handling
- collector output can make evidence easier to find but cannot judge whether it is sufficient
- failed commands may still need human classification as true failures, environment limitations, or expected benchmark findings

## 7. OPT-04 Handoff

Recommended next node:

```text
OPT-04 - UI Mockup-First Small Benchmark
```

Small OPT-04 boundary:

- compare a tiny UI mockup-to-code workflow against the current manual UI specification style
- include a UI Contract alongside any mockup
- keep the mockup from becoming the sole specification
- avoid product direction changes
- avoid live Bridge, GitHub write, Dispatcher, Runner, Codex runtime task execution, RV2-04, services, watchers, or MCP
- preserve raw evidence and reviewer judgment
