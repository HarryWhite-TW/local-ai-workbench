# Product Direction Alignment (#204)

## 1. Purpose

This note records the product direction alignment after the Local Workbench baseline became runnable and reviewable.

The project should now be treated as both:

- a public portfolio engineering project
- a product-shaped local-first knowledge workbench prototype

This note does not add a new boundary layer and does not implement GitHub writeback, Result Packet write, runner, dispatcher, watcher, background automation, external LLM calls, or Obsidian integration.

## 2. Current Baseline

The current application baseline is a local document workbench:

- configure one local root folder
- manually scan supported local documents
- index documents into SQLite
- list indexed documents
- search by title, relative path, and extracted content
- open document details
- generate deterministic single-document summary artifacts
- review audit context

Recent manual validation confirmed:

- API tests passed
- Web build passed
- API and Web can run together on localhost
- a demo local folder can be scanned
- indexed documents can be selected
- document detail and deterministic summary can be displayed
- audit events are visible in the UI

## 3. Product Reframe

The next product direction is:

```text
Local AI Workbench is a local-first document-to-knowledge workbench.
It helps a user turn local documents into searchable, reviewable, summarizable,
auditable, and exportable personal knowledge assets.
This reframes the project from only "local document browsing" toward a more useful local knowledge workflow.

The product value should come from the full chain:

local documents
-> local indexing
-> local search
-> deterministic summary
-> audit context
-> knowledge export
-> personal workflow integration
4. Why Obsidian Bridge Is The First Product Extension

The workbench already creates useful document-derived artifacts, especially document details, summaries, and audit context.

The next practical product question is:

Where should the generated knowledge go after it is created?

Obsidian is a natural first target because it uses local Markdown files and fits a personal knowledge workflow.

The first Obsidian-related feature should not be a plugin, background sync system, or automation pipeline.

The first version should be:

manual trigger
one-way export
local Markdown output
preview before write
no background watcher
no two-way sync
no external LLM dependency
no modification of original source documents
5. Intended Development Sequence

The next product work should proceed in this order:

#205 Obsidian Export Core

Create a pure core function that converts local workbench data into Markdown text.

Initial scope:

document detail + summary artifact + selected audit metadata
-> Obsidian-compatible Markdown string

No file write, no API route, and no UI in this step.

#206 Obsidian Export Preview API

Expose a local preview endpoint that returns the generated Markdown.

This preserves the preview-before-write model.

#207 Obsidian Export Write API

Add a controlled local write endpoint that writes the approved Markdown to a user-selected export folder.

This must not modify original source documents.

#208 Obsidian Export UI Hook

Add a UI action from the document detail or summary area.

The UI should allow the user to preview the generated note before exporting.

#209 Product UX Improvement

Improve daily-use value around search, summary display, empty states, and first-run clarity.

#210 Product Demo And Portfolio Polish

Update README, screenshots, and portfolio explanation after the product value path is clearer.

6. Out Of Scope For This Phase

The following remain out of scope for this phase:

Obsidian plugin
two-way sync
background folder watcher
automatic mass export
external LLM call
semantic search or vector database
n8n-style pipeline
multi-user SaaS framing
GitHub writeback
Result Packet write
runner, dispatcher, or watcher behavior
automatic commit or push
7. Decision

Adopt the product direction:

Local Document Assistant Prototype
-> Local Document-to-Knowledge Workbench
-> Obsidian one-way Markdown export as the first value extension

The next implementation issue should be #205 Obsidian Export Core.
