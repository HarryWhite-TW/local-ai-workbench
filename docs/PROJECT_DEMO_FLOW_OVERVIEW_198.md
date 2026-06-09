# Project Demo Flow Overview (#198)

## 1. Purpose

This document provides a concise reviewer-facing demo flow for Local AI Workbench after the #197 boundary-chain completion decision and the #204 product direction alignment.

#198 is normal project work.

This document is not a new boundary layer.

#200 continues normal project work by refreshing reviewer-facing demo commands after #199 stabilized local CLI demo usage for Python 3.10-compatible environments.

This document does not implement GitHub writeback, Result Packet write, runner, dispatcher, watcher, or automation behavior.

## 2. Current Project Positioning

The repo is a localhost, single-user, local document-to-knowledge workbench.

It has two useful reviewer angles:

- the visible document-to-knowledge workbench: configure one folder, scan local documents, search, inspect document detail, generate deterministic summary artifacts, preview Obsidian-ready Markdown, check export destination status, export local `.md` notes, and review audit context
- the local workflow control layer: explicit task/result/readback surfaces, validation dry-runs, dry-run previews, approval records, readiness gates, and implementation-boundary validation

The bridge utilities are evidence and review tools. They do not turn the repo into uncontrolled automation.

## 3. Safe Local Demo Flow

A safe reviewer demo can use this order:

1. Start the API locally.
2. Start the web UI locally.
3. Configure one local root folder.
4. Run a manual document scan.
5. Search indexed documents.
6. Open one document detail view.
7. Generate or inspect a deterministic summary artifact.
8. Preview an Obsidian-ready Markdown note for the selected document.
9. Paste an existing local destination folder, such as an Obsidian Vault inbox.
10. Run destination intelligence to verify whether the destination is an Obsidian Vault root, inside a vault, a normal Markdown folder, or not exportable.
11. Export the Markdown file after preview and destination check.
12. Review the audit context in the UI.
13. Run local-only bridge CLI commands to show the validation/readback model.
14. Optionally validate a temporary local JSON artifact outside the repo.

The demo does not require GitHub writeback.

The demo does not call GitHub.

The demo does not write GitHub comments.

The demo does not require Result Packet write.

The demo does not require runner, dispatcher, watcher, or automation behavior.


The Obsidian-ready export demo writes a normal local Markdown file. It includes destination intelligence for Obsidian Vault roots, folders inside a vault, normal Markdown folders, and invalid destinations. It does not require an Obsidian plugin, Obsidian API integration, two-way sync, or a background watcher.


## 4. Key CLI Entry Points

Safe local/readback examples:

```powershell
$env:PYTHONPATH='src'; python -m local_runner_bridge.result_surface_cli --sample
```

```powershell
$env:PYTHONPATH='src'; python -m local_runner_bridge.writeback_target_contract_cli --help
```

```powershell
$env:PYTHONPATH='src'; python -m local_runner_bridge.writeback_implementation_boundary_cli --help
```

Other committed local-only validators use local JSON files:

- `local_runner_bridge.writeback_target_contract_cli --contract-file <local-json>`
- `local_runner_bridge.writeback_dry_run_preview_cli --contract-file <local-json> --result-surface-file <local-json> --preview-content <text>`
- `local_runner_bridge.approval_record_cli --approval-record-file <local-json>`
- `local_runner_bridge.readiness_gate_cli --readiness-file <local-json>`
- `local_runner_bridge.writeback_implementation_boundary_cli --boundary-file <local-json>`

These commands are for reviewer verification and local validation/readback evidence. They do not call GitHub, write GitHub comments, write Result Packets, invoke runner/dispatcher/watcher behavior, or add a new boundary layer.

## 5. What A Reviewer Can Verify

A reviewer can verify:

- the app is positioned as a local document-to-knowledge workbench
- the API and web UI run on localhost
- document scan is manual
- summaries are deterministic local artifacts
- Obsidian-ready exports are local Markdown files written after preview and destination check
- bridge utilities emit JSON to stdout
- local validators fail closed around missing or unsafe fields
- the safety chain is documented without claiming real writeback
- #197 says to stop adding boundary layers and return to normal project work

## 6. What Remains Forbidden

The following remain forbidden unless separately approved later:

```text
GitHub writeback implementation
GitHub comment write
GitHub issue body update
Result Packet write implementation
Codex-side action execution
runner behavior
dispatcher behavior
watcher behavior
broad issue scan
next/latest issue inference
autonomous execution
automatic commit
automatic push
PR creation
merge
issue close
label change
approval chaining
real write mode
new boundary layer expansion
Obsidian plugin behavior
Obsidian two-way sync
background Obsidian watcher
```

Future GitHub writeback is still not implemented and still requires a later explicit Strict Lane decision.

## 7. Suggested Next Practical Tasks

Recommended practical tasks after #198:

- add a small architecture map for the local workbench and bridge utilities
- create a short demo script for portfolio review
- keep README and demo flow aligned with current product behavior
- improve export result visibility and copy-friendly path display
- polish screenshot captions, README flow, and export UI presentation
- add CLI usage examples for local-only bridge commands
- clean up test coverage around preview, approve, and audit behavior
- write a lightweight developer onboarding guide
- document the issue workflow as a project-management example

The next work should prioritize visible project value, not more boundary layering.
