# UI Presentation Redesign Plan (#219)

## 1. Purpose

This document records the next UI direction for Local AI Workbench after the export destination intelligence and export result visibility work.

The goal is not to add a new backend feature. The goal is to improve the product presentation layer so the app feels closer to a usable local-first workbench instead of a plain card-based prototype.

## 2. Current UI Problems

### 2.1 Layout And UX Are Coupled Too Tightly

The current three-column layout makes the right panel too narrow for export paths, destination status, Markdown preview, and audit context.

This causes:

* long paths to wrap poorly
* export actions to feel cramped
* audit content to push useful export information too far down
* the center panel to have too much empty space when documents are short
* users to rely too heavily on vertical scrolling

### 2.2 Flexibility Is Too Limited

The current UI does not provide user-facing display controls.

Missing flexibility includes:

* no light / dark / soft theme toggle
* no Chinese / English language toggle
* no compact / comfortable display mode
* no panel-level focus mode
* no persistent UI preference state

These are presentation-layer concerns and should not affect backend behavior.

### 2.3 Visual Style Feels Too Prototype-Like

The current interface is readable, but visually simple. The UI feels like stacked cards instead of a product-shaped workbench.

Visible weaknesses include:

* weak visual hierarchy
* repeated card patterns
* limited section identity
* low interaction feedback
* low demo polish
* limited reviewer-facing product impression

### 2.4 Interaction Is Functional But Not Product-Like

The app has functional interactions, but not enough presentation interactions.

Existing interactions include search, document selection, summary generation, Markdown preview, destination check, export, copy path, and collapsible details.

Missing interaction polish includes:

* tabbed right-side assistant panel
* clearer active states
* export success feedback
* copy feedback beyond button text
* animated or visually distinct state transitions
* collapsible audit context
* focused display modes

## 3. Redesign Principles

### 3.1 Keep The Current Product Mainline

The UI redesign must support the existing product identity:

```text
Local Document-to-Knowledge Workbench
```

The redesign should make the current value chain clearer:

```text
local documents
-> local indexing
-> local search
-> document detail
-> deterministic summary
-> audit context
-> Obsidian-ready Markdown export
```

### 3.2 Do Not Expand Product Scope

The redesign must not introduce:

* Obsidian plugin behavior
* Obsidian API integration
* two-way sync
* background watcher
* autonomous file operations
* external LLM calls
* large UI dependency migration

### 3.3 Improve Presentation Without Breaking Workflow

The current working flow must remain valid:

```text
configure folder
-> scan
-> select document
-> generate summary
-> preview Markdown
-> check destination
-> export Markdown
-> review audit
```

### 3.4 Prefer Small, Reviewable Changes

Each implementation issue should be small enough to validate with:

* `npm run build`
* `pytest tests/api`
* visual runtime smoke
* git diff scope check

## 4. Proposed Redesign Direction

### 4.1 Layout Shell Redesign

Replace the current rigid three-column feeling with a clearer workbench shell.

Suggested structure:

```text
Top:
  Workspace title
  root folder status
  scan action
  display controls

Left:
  Search
  Documents

Center:
  Document detail
  extracted content

Right:
  Assistant panel with tabs:
    Summary
    Export
    Audit
```

The right panel should stop stacking Summary, Export, and Audit vertically.

Instead, it should use tabs:

```text
[Summary] [Export] [Audit]
```

This should reduce vertical scroll and improve task focus.

### 4.2 Theme System

Add a small CSS-variable based theme system.

Initial modes:

* Light
* Soft
* Dark

Requirements:

* store selected theme in localStorage
* avoid external UI libraries
* keep colors centralized in CSS variables
* default to current light or soft appearance

### 4.3 Language Toggle

Add a simple language mode:

* Traditional Chinese
* English

Requirements:

* store selected language in localStorage
* keep translation strings close to the frontend
* avoid full i18n dependency for now
* do not translate backend data values
* preserve technical labels where useful

### 4.4 Interaction Polish

Add small visual interactions:

* active tab state
* hover states
* compact success feedback
* export result emphasis
* collapsible audit by default
* smoother empty states
* clearer disabled states
* optional toast-like feedback for copy/export success

## 5. Suggested Implementation Issues

### #220 Layout Shell Redesign

Purpose:

Improve the core screen structure without changing backend behavior.

Scope:

* `web/src/App.tsx`
* `web/src/index.css`

Expected result:

* right panel uses Summary / Export / Audit tabs
* export panel no longer competes vertically with audit
* layout feels more like a workbench
* existing scan/search/summary/export flow still works

### #221 Theme And Language Toggle

Purpose:

Add user-facing display flexibility.

Scope:

* theme state
* language state
* localStorage persistence
* CSS variables
* small translation dictionary

Expected result:

* user can switch visual theme
* user can switch Chinese / English UI copy
* preference persists after refresh

### #222 Interaction Polish

Purpose:

Improve perceived product quality.

Scope:

* hover / active states
* export success feedback
* copy path feedback
* better empty states
* smoother collapsible sections
* audit panel presentation improvements

Expected result:

* the app feels less static
* demo presentation improves
* core workflow remains unchanged

## 6. Validation Plan

Each implementation issue should pass:

```powershell
cd web
npm run build
cd ..

.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/api

git status --short
git diff --name-only
git diff --check
```

Runtime smoke should verify:

* root folder save still works
* scan still works
* search still works
* document selection still works
* summary generation still works
* Markdown preview still works
* destination check still works
* export still works
* audit still appears
* theme/language preferences persist when implemented

## 7. Decision

The next product direction should pause backend expansion and focus on UI presentation quality.

Recommended next issue:

```text
#220 Layout Shell Redesign
```

Reason:

The current layout is the main bottleneck. Theme, language, and interaction polish will be more effective after the layout shell is improved.
