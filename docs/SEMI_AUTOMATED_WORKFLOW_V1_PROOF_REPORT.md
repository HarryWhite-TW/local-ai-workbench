# Semi-automated Workflow v1 Proof Report

## Purpose

This report summarizes the proof state of Semi-automated workflow v1.

The goal is to record what has been validated, what remains limited, and what should happen next.

This report closes the current workflow governance phase and prepares the next phase: Local Runner Bridge v0.

This report is a proof and alignment document.

This report does not authorize automatic commit.

This report does not authorize automatic push.

This report does not authorize automatic issue close.

This report does not authorize automatic PR creation.

This report does not authorize automatic merge.

This report does not authorize approval chaining.

This report does not authorize full autonomous agent behavior.

## Roadmap anchor

#114 is the roadmap anchor for Semi-automated workflow v1.

The workflow target is:

```text
User
??ChatGPT
??GitHub Issue / Comment
??Codex Web / Codex / local runner
??GitHub result
??ChatGPT review
??User approval only for key high-risk decisions
```

The current target is not Lv5 full automation.

The current target is a ChatGPT-centered semi-automated workflow with explicit user approval for high-risk actions.

## Completed evidence

The current workflow has validated the following evidence:

* ChatGPT can prepare scoped Codex prompts.
* Codex can execute bounded tasks when explicitly scoped.
* GitHub can act as a task and audit layer.
* ChatGPT can review GitHub-visible commits.
* ChatGPT can review GitHub-visible remote files.
* ChatGPT can detect conflicts between marker evidence and remote file content.
* Short structured fallback reports can be used when comment readback is unavailable or unstable.
* Local commit, push, and final audit can remain separate phases.
* User approval can remain required for high-risk actions.
* No full autonomous agent behavior is required for the current workflow.

## Completed roadmap items

The following roadmap items have been completed or functionally validated under #114.

## #119 Away-to-Home adoption packets

#119 established the Away-to-Home adoption packet concept.

Purpose:

* allow Away Mode candidate work
* preserve Home Mode safety boundaries
* prevent local commit and push from non-primary environments
* define how candidate results are handed back to the primary machine
* keep ChatGPT review as the decision layer

Proof result:

* Away-to-Home handoff is now represented as a document.
* The workflow can distinguish Away Mode candidate work from Home Mode commit and push phases.
* High-risk local Git actions remain Home Mode only.

## #120 GitHub readback proof

#120 established GitHub readback proof.

Purpose:

* reduce the need for the user to paste long Codex output
* allow ChatGPT to review GitHub-visible evidence directly
* define valid readback surfaces
* define fallback rules when connector readback is unavailable

Proof result:

* remote commit readback works
* remote file readback works
* marker evidence is useful but not sufficient when file content matters
* remote readback wins when marker evidence and remote file content disagree
* short structured fallback reports are allowed when GitHub comment readback is unstable

Important limitation:

GitHub issue comment marker readback has been observed as unstable through the connector.

The workflow must not depend exclusively on issue comment search.

## #121 Low-risk closed-loop smoke

#121 validated a low-risk closed-loop smoke path.

Purpose:

* verify a bounded low-risk action
* write a GitHub-visible result
* return control to ChatGPT for review
* avoid repo file changes
* avoid commit
* avoid push
* avoid issue close

Proof result:

* the low-risk smoke was completed through fallback-assisted diagnostic review
* the short structured diagnostic report included comment URL, comment ID, marker first line, and no high-risk action flags
* no repo file change, commit, push, PR, merge, issue close, or label change was allowed

Important limitation:

#121 should be described as fallback-assisted success, not pure connector readback success.

## #122 High-risk approval package standard

#122 established the high-risk approval package standard.

Purpose:

* standardize approval packages before commit, push, close, PR creation, merge, label change, or future approval-consuming actions
* require explicit phase-specific user approval
* forbid approval chaining
* preserve separate approval gates

Proof result:

* high-risk approval package fields are now documented
* change summary, expected result, risk level, possible risks, validation evidence, rollback note, forbidden operations, and stop condition are required
* commit approval does not approve push
* push approval does not approve issue close
* each high-risk action requires a separate approval package and separate user approval
* approval chaining is forbidden

## Current workflow capability

The current workflow can support:

* scoped task planning
* docs-only ReviewBundle work
* local commit approval package
* push approval package
* final audit
* GitHub commit readback
* GitHub remote file readback
* fallback-assisted marker review
* user-retained high-risk approval

The current workflow is suitable for controlled project execution where ChatGPT is the planning and review layer and Codex is a bounded execution layer.

## Current workflow limitations

The current workflow does not yet provide:

* full autonomous execution
* background watcher behavior
* always-on polling
* automatic commit
* automatic push
* automatic issue close
* automatic PR creation
* automatic merge
* unrestricted Codex execution
* broad issue scanning
* reliable pure connector readback for every issue comment marker
* automatic delivery of ChatGPT prompts into the local Codex App
* automatic task pickup by a local runner

The workflow should continue to treat comment marker readback as helpful but not absolute.

When content matters, remote file readback is stronger than marker evidence.

When remote state matters, remote commit or branch readback is stronger than marker evidence.

## Safety boundaries

The following safety boundaries remain active:

* no automatic commit
* no automatic push
* no automatic issue close
* no automatic PR creation
* no automatic merge
* no approval chaining
* no broad issue scanning
* no background watcher
* no always-on polling
* no unrestricted Codex execution
* no Lv5 full automation
* no expansion of runtime authority
* no expansion of runner authority
* no expansion of dispatcher authority
* no expansion of automation authority

High-risk actions must remain separate phases.

User approval remains required for high-risk actions.

## Evidence hierarchy

The workflow should use the following evidence hierarchy:

1. Remote file readback when file content matters.
2. Remote commit readback when pushed state matters.
3. Branch or HEAD readback when repository state matters.
4. GitHub-visible marker when phase status matters.
5. Short structured fallback report when connector comment readback is unavailable or unstable.
6. Long transcript only when diagnosis requires it.

Marker evidence is useful for review.

Marker evidence is not authority by itself.

Marker evidence does not replace remote readback when content or remote state matters.

## Fallback-assisted review

Fallback-assisted review is allowed when:

* GitHub issue comment search is delayed
* GitHub issue comment fetch is truncated
* connector readback is unavailable
* marker comment URL or comment ID is available from the executor
* the fallback report is short and structured
* the fallback report includes no high-risk action violations

Fallback-assisted review should be explicitly labeled when used.

Fallback-assisted review should not be presented as pure connector readback success.

## Direction change after proof report

The next phase should move from workflow governance documentation to task handoff automation.

The next target is Local Runner Bridge v0.

The goal of Local Runner Bridge v0 is to reduce manual copy and paste between ChatGPT, Codex, and GitHub.

The target flow is:

```text
ChatGPT
??GitHub task packet
??local runner
??bounded local action
??GitHub result packet
??ChatGPT review
??user approval for high-risk phases
```

Local Runner Bridge v0 should automate task handoff, not high-risk approval.

It should not introduce automatic commit, automatic push, automatic close, background watcher behavior, or Lv5 full automation.

## Local Runner Bridge v0 scope

Local Runner Bridge v0 should begin with:

* manual trigger only
* one explicit task packet
* one explicit result packet
* one repository
* one branch
* allowlist actions only
* fail-closed policy
* no background watcher
* no always-on polling
* no broad issue scanning
* no automatic high-risk action

The first useful MVP should reduce long prompt copy and paste for docs-only ReviewBundle work.

## Recommended next issue sequence

The recommended next issue sequence is:

## #124 Local Runner Bridge v0 architecture

Define the architecture before writing executable code.

Expected output:

* ChatGPT responsibility boundary
* GitHub task and audit boundary
* local runner responsibility boundary
* Codex responsibility boundary
* user approval boundary
* fail-closed rules
* future Lv5 expansion points

Expected file:

* docs/LOCAL_RUNNER_BRIDGE_V0_ARCHITECTURE.md

## #125 Local Runner Task Packet v1

Define the task packet schema.

Expected output:

* task marker
* task id
* logical issue
* action type
* risk level
* allowed files
* forbidden operations
* expected branch
* expected head
* approval requirement
* stop condition

Expected files:

* docs/LOCAL_RUNNER_TASK_PACKET_V1.md
* docs/examples/local_runner_task_packet.example.md

## #126 Local Runner Result Packet v1

Define the result packet schema.

Expected output:

* result marker
* result status
* changed files
* commit created flag
* push performed flag
* evidence fields
* failure reason
* next recommended action

Expected files:

* docs/LOCAL_RUNNER_RESULT_PACKET_V1.md
* docs/examples/local_runner_result_packet.example.md

## #127 Local Runner Policy Engine v0

Define the safety policy before implementation.

Expected output:

* action allowlist
* risk mapping
* approval requirement handling
* forbidden operations
* branch and HEAD guards
* file scope guards
* fail-closed behavior
* evidence hierarchy

Expected file:

* docs/LOCAL_RUNNER_POLICY_ENGINE_V0.md

## #128 Read-only Runner MVP

Implement the first read-only runner.

Expected behavior:

* read one task packet
* validate repository identity
* validate branch and HEAD
* run read-only repo checks
* produce a result packet
* perform no repo file changes
* perform no commit
* perform no push

Expected files may include:

* scripts/local_runner_bridge_v0.py
* tests/test_local_runner_bridge_readonly.py

## #129 GitHub Result Writeback MVP

Allow the runner to write a result packet back to GitHub.

Expected behavior:

* create a GitHub-visible result comment
* return comment URL or comment ID
* preserve local fallback output
* fail safely if GitHub writeback fails

## #130 Docs-only Apply Candidate MVP

Allow the runner to apply one docs-only candidate.

Expected behavior:

* read BEGIN_DOCUMENT content from a task packet
* write only the allowed file
* do not stage
* do not commit
* do not push
* run diff checks
* write ReviewBundle result

## #131 Commit Rail MVP

Allow the runner to perform an explicitly approved local commit.

Expected behavior:

* require commit approval task
* stage exact allowed file only
* create exactly one local commit
* write LOCAL-COMMIT-AUDIT result
* do not push

## #132 Push Rail MVP

Allow the runner to perform an explicitly approved push.

Expected behavior:

* require push approval task
* verify local head
* verify origin/master
* verify ahead by exactly one commit
* push origin master
* write PUSH-AUDIT result
* do not create new commits
* do not close issues

## #133 Final Audit Rail

Allow the runner to assist final audit.

Expected behavior:

* verify HEAD equals origin/master
* verify remote file content
* verify no PR, merge, issue close, or label change
* write FINAL-AUDIT result

## #134 End-to-End Smoke

Run one complete controlled flow.

Expected behavior:

* ChatGPT creates a task packet
* runner reads the task packet
* runner applies a docs-only candidate
* ChatGPT reviews result
* user approves commit
* runner commits
* ChatGPT reviews commit
* user approves push
* runner pushes
* ChatGPT performs final review

## #135 Workflow Kit v1.0 packaging

Package the workflow for reuse.

Expected output:

```text
workflow-kit/
  README.md
  AGENTS_SNIPPET.md
  PROJECT_INSTRUCTIONS_SNIPPET.md
  ROADMAP_ISSUE_TEMPLATE.md
  REVIEWBUNDLE_PROMPT_TEMPLATE.md
  COMMIT_APPROVAL_TEMPLATE.md
  PUSH_APPROVAL_TEMPLATE.md
  FINAL_AUDIT_TEMPLATE.md
  MARKER_DIAGNOSTIC_TEMPLATE.md
  ADOPTION_CHECKLIST.md
```

## #136 Cross-project adoption smoke

Test the workflow in another low-risk repository.

Expected behavior:

* install or copy the Workflow Kit
* create a roadmap anchor issue
* run one read-only task
* run one docs-only candidate
* verify ChatGPT can review the GitHub result

## Future Lv5 expansion compatibility

Local Runner Bridge v0 should preserve future upgrade paths.

The architecture should reserve room for:

* queue manager
* approval ledger
* multi-issue scheduler
* multi-repo support
* background watcher adapter
* automatic low-risk execution
* human approval inbox
* rollback planner
* policy profiles
* evidence store

These should remain future-facing.

They are not authorized by this report.

Any Lv5 or beyond capability requires separate design, review, and explicit approval.

## Recommended future packaging

After this proof report is accepted, the workflow should eventually be packaged as a reusable Workflow Kit.

The recommended package form is:

```text
workflow-kit/
  README.md
  AGENTS_SNIPPET.md
  PROJECT_INSTRUCTIONS_SNIPPET.md
  ROADMAP_ISSUE_TEMPLATE.md
  REVIEWBUNDLE_PROMPT_TEMPLATE.md
  COMMIT_APPROVAL_TEMPLATE.md
  PUSH_APPROVAL_TEMPLATE.md
  FINAL_AUDIT_TEMPLATE.md
  MARKER_DIAGNOSTIC_TEMPLATE.md
  ADOPTION_CHECKLIST.md
```

For repository adoption, the recommended in-repo layout is:

```text
docs/workflow/
  SEMI_AUTOMATED_WORKFLOW_V1.md
  GITHUB_READBACK_PROOF.md
  HIGH_RISK_APPROVAL_PACKAGE_STANDARD.md
  AWAY_TO_HOME_ADOPTION_PACKETS.md
  WORKFLOW_ADOPTION_GUIDE.md
  WORKFLOW_PROMPT_TEMPLATES.md
```

The Workflow Kit should start as a document template and prompt template package.

The Workflow Kit should not start as a script-driven automation tool.

Scripted setup may be considered later only after separate design, review, and explicit approval.

## Adoption guidance for other projects

To adopt the workflow in another project, the user should define:

* repository name
* default branch
* roadmap anchor issue
* allowed file paths
* forbidden file paths
* risk rules
* commit message convention
* issue comment marker convention
* fallback short report policy
* high-risk approval policy

A new project should first run a low-risk ReviewBundle task before using commit or push phases.

A new project should not assume that this workflow authorizes automatic Git operations.

## Recommended next phase

After #123 is complete, do not immediately expand automation authority.

The next recommended phase is #124 Local Runner Bridge v0 architecture.

The next phase should design the bridge before writing runner code.

The recommended order is:

1. #124 architecture
2. #125 task packet schema
3. #126 result packet schema
4. #127 policy engine
5. #128 read-only runner MVP
6. #129 GitHub result writeback MVP
7. #130 docs-only apply candidate MVP
8. pause and evaluate whether copy-paste reduction is meaningful
9. continue to commit and push rails only if the MVP is stable

## Current status

Semi-automated workflow v1 is functionally validated for controlled ChatGPT-centered project execution.

The workflow is not full autonomous automation.

The workflow is not Lv5.

The workflow is suitable for bounded Codex execution with ChatGPT review and user-controlled high-risk approval gates.

The next strategic goal is Local Runner Bridge v0, focused on reducing manual task handoff and copy-paste overhead.

This report should be used as the closing proof report for #114 before starting #124.
