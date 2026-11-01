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

local documents
-> local indexing
-> local search
-> reviewable document details
-> deterministic summary
-> audit context
-> knowledge export
-> personal workflow integration
3. Current Phase

The current phase is:

Obsidian-ready Markdown Export MVP consolidation

The current export feature is:

Obsidian-ready Markdown Export
+ Export Destination Intelligence

It means:

generate Markdown from local document detail, summary, and audit context
preview Markdown before writing
check whether the destination is an Obsidian Vault root, inside an Obsidian Vault, a normal Markdown folder, missing, or not a directory
show a human-readable destination status
expose developer-readable destination details
write the Markdown file to a user-selected local folder
support using an Obsidian Vault folder or inbox folder as the destination
avoid implying that the app is an Obsidian plugin or sync engine

It does not mean:

Obsidian plugin
Obsidian API integration
two-way sync
background watcher
automatic mass export
automatic opening of Obsidian
4. Completed Work Since Direction Alignment
#204 Product Direction Alignment

Reframed the project as both a public portfolio project and a product-shaped local-first knowledge workbench prototype.

#205 Obsidian Export Markdown Core

Added pure Markdown generation core.

#206 Obsidian Export Preview API

Added local preview endpoint.

#207 Obsidian Export Write API

Added approved local write endpoint, avoided overwriting existing files, and added export audit events.

#208 Obsidian Export UI Hook

Added frontend UI for previewing and exporting Markdown.

#209 Obsidian Export UX Polish

Added clearer export flow guidance and distinguished data source/root folder from export folder.

#210 Remember Obsidian Export Folder

Remembered the export folder in frontend localStorage.

#211 Obsidian-ready Export UX Boundary

Clarified that the feature is Obsidian-ready Markdown export, not plugin, sync, or API integration.

#213 README And Demo Flow Sync

Updated public documentation for the Obsidian-ready Markdown Export MVP.

#214 Export Destination Intelligence Design

Defined human-readable and developer-readable destination status behavior.

#215 Export Destination Intelligence Core And API

Added destination detection for Obsidian Vault root, inside Obsidian Vault, plain Markdown folder, missing folder, and non-directory paths.

#216 Export Destination Intelligence UI

Added frontend destination status card, check destination action, and collapsible developer details.

5. Next Planned Issues
#217 README And Demo Flow Sync For Export Destination Intelligence

Purpose:

Update public documentation so GitHub readers understand the destination intelligence behavior shipped in #214-#216.

Scope:

README.md
docs/PROJECT_DEMO_FLOW_OVERVIEW_198.md
docs/CURRENT_PRODUCT_ROADMAP_212.md

Expected content:

Local Document-to-Knowledge Workbench positioning
Obsidian-ready Markdown Export with destination intelligence
scan -> summary -> preview -> check destination -> export -> audit
clear non-goals:
not an Obsidian plugin
not Obsidian API integration
not two-way sync
not background automation
#218 Export Result Visibility / Path Copy UX

Purpose:

Make exported results easier to inspect, copy, and explain from the UI.

Possible scope:

show last exported filename as a separate field
show exported path in a cleaner result area
provide copy-friendly path display
show duplicate-file recovery instructions
keep the feature local-first and manual
#219 UI Presentation Polish

Purpose:

Improve the visual presentation of the workbench without changing the product scope.

Possible scope:

improve export panel layout
reduce long-path visual noise
make audit context less dominant
improve empty states and reviewer-facing visual hierarchy
Future Consideration: Obsidian Integration Design

This should remain design-only unless separately approved.

Possible future ideas:

Obsidian URI open-note helper
Vault picker
frontmatter template refinement
Obsidian plugin concept note

Non-goals remain:

plugin implementation
sync engine
watcher
modifying .obsidian
automatic background export
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
a lower-layer capability required by the plan does not exist yet
