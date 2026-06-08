# Current Product Roadmap (#212)

## 1. Purpose

This roadmap records the current product direction, completed work, next planned issues, and route-change rules for Local AI Workbench.

It exists to make future work traceable.

Future work should not be justified only by "this seems reasonable now." It should be justified by how it supports the current product mainline, unless a route-change condition is explicitly met.

## 2. Current Product Mainline

The current product mainline is:

```text
Local Document-to-Knowledge Workbench

The project should help a user turn local documents into:

searchable local records
reviewable document details
deterministic summaries
audit-tracked local actions
exportable personal knowledge assets

The product value chain is:

local documents
-> local indexing
-> local search
-> deterministic summary
-> audit context
-> knowledge export
-> personal workflow integration
3. Current Phase

The current phase is:

Obsidian-ready Markdown Export MVP consolidation

This phase is not a full Obsidian integration phase.

The current export feature is:

Obsidian-ready Markdown Export

It means:

generate Markdown from local document detail, summary, and audit context
preview Markdown before writing
write the Markdown file to a user-selected local folder
support using an Obsidian Vault folder as the destination
avoid implying that the app is an Obsidian plugin or sync engine

It does not mean:

Obsidian plugin
Obsidian API integration
vault-aware validation
two-way sync
background watcher
automatic mass export
4. Completed Work Since Direction Alignment
#204 Product Direction Alignment

Outcome:

Reframed the project as both a public portfolio project and a product-shaped local-first knowledge workbench prototype.
Selected one-way Markdown export as the first product extension.
#205 Obsidian Export Markdown Core

Outcome:

Added pure Markdown generation core.
Converted document detail, summary artifact, and selected audit metadata into Markdown text.
No file write, no route, no UI.
#206 Obsidian Export Preview API

Outcome:

Added local preview endpoint.
Returned Markdown preview for a selected document.
Preserved preview-before-write behavior.
#207 Obsidian Export Write API

Outcome:

Added approved local write endpoint.
Required explicit approval.
Wrote Markdown to a selected local export folder.
Avoided overwriting existing files.
Added audit event for export writes.
#208 Obsidian Export UI Hook

Outcome:

Added frontend UI for previewing and exporting Markdown.
Verified runtime export produced an actual .md file.
Confirmed duplicate-file protection worked.
#209 Obsidian Export UX Polish

Outcome:

Added clearer export flow guidance.
Distinguished data source/root folder from export folder.
Collapsed Markdown preview.
Improved duplicate-export guidance.
#210 Remember Obsidian Export Folder

Outcome:

Remembered the export folder in frontend localStorage.
Reduced repeated manual input during normal use.
#211 Obsidian-ready Export UX Boundary

Outcome:

Clarified that the feature is Obsidian-ready Markdown export.
Avoided implying plugin, sync, or vault-aware integration.
5. Next Planned Issues
#213 README And Demo Flow Sync

Purpose:

Update public documentation so GitHub readers understand the current product value.

Scope:

README.md
docs/PROJECT_DEMO_FLOW_OVERVIEW_198.md

Expected content:

Local Document-to-Knowledge Workbench positioning
Obsidian-ready Markdown Export flow
scan -> summary -> preview -> export -> audit
clear non-goals:
not an Obsidian plugin
not two-way sync
not background automation

Why next:

The product capability changed after #205-#211. Public docs should match current implementation before the next feature expansion.

#214 Vault-aware Export Validation

Purpose:

Start moving from generic Markdown export toward more Obsidian-aware behavior without building a plugin.

Possible scope:

detect whether export folder is inside or near an Obsidian Vault
identify .obsidian folder when available
show whether the destination is:
Obsidian Vault folder
folder inside an Obsidian Vault
normal Markdown folder
still allow plain Markdown export

Why after #213:

The current feature boundary must be clearly documented before adding vault-aware behavior.

#215 Export Result Visibility

Purpose:

Make exported results easier to inspect from the UI.

Possible scope:

show last exported filename
show exported path in a cleaner result area
show duplicate-file recovery instructions
optionally show copyable path text

Why after #214 or alongside it:

Export result clarity improves day-to-day usability but should not expand into background file management.

#216 Search And Summary UX Improvement

Purpose:

Improve core daily-use workflow outside export.

Possible scope:

clearer summary state
better search result context
improved empty states
more useful summary display sections

Why later:

The export MVP should finish documentation and destination clarity first.

6. Priority Rules

When choosing the next issue, use this order:

Product mainline fit
User task completion
Safety and local-first constraints
Scope control
Demo and portfolio value
Visual polish
New feature expansion

A task should not be prioritized only because it is easy, attractive, or currently visible.

7. Route-change Rules

The roadmap may change when at least one condition is true:

runtime validation reveals a blocker
user explicitly changes the product goal
implementation exposes a safety or data-loss risk
current UX causes repeated task failure
documentation no longer matches shipped behavior
a planned feature depends on missing lower-layer capability

When the route changes, the reason should be recorded in the next issue note or commit summary.

8. Current Non-goals

The following are not current-phase goals:

Obsidian plugin
two-way sync
background watcher
automatic mass export
external LLM integration
semantic search or vector database
n8n-style workflow automation
GitHub writeback
Result Packet write
runner, dispatcher, or watcher expansion
multi-user SaaS behavior
9. Current Decision

The next issue should be:

#213 README And Demo Flow Sync

Reason:

The current product implementation now includes an Obsidian-ready Markdown export flow. Public documentation should be updated before adding vault-aware validation or more export features.
