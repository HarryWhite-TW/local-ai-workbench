# Export Destination Intelligence Design (#214)

## 1. Purpose

This design note defines the next product step after Obsidian-ready Markdown Export MVP consolidation.

The goal is to make export destination status understandable for both:

- non-developer users who need a clear result and next step
- developer/reviewer users who need inspectable technical details

This issue does not implement the feature yet.

It defines the product behavior for the next implementation issue.

## 2. Product Mainline Fit

The current product mainline is:

```text
Local Document-to-Knowledge Workbench

The current export capability is:

Obsidian-ready Markdown Export

The next step should improve destination understanding before expanding export behavior.

The product problem is:

A user can paste an export folder path, but the app currently does not explain what kind of destination it is.

This creates confusion between:

a plain Markdown folder
an Obsidian Vault root
a folder inside an Obsidian Vault
an invalid or missing folder
3. Design Principle

Every technical result should have two surfaces:

Human-readable surface
Developer-readable surface

The human-readable surface answers:

Is this destination usable?
Is it an Obsidian-related destination?
Can I export here?
What should I do next?

The developer-readable surface answers:

What path was checked?
Does the path exist?
Is it a directory?
Was a .obsidian folder found?
What vault root was detected?
Which destination type was assigned?
Was export allowed?
4. Destination Types

The implementation should classify export folder destinations into the following types.

4.1 Obsidian Vault Root

Condition:

export_folder/.obsidian exists and is a directory

Human result:

Obsidian vault detected. Markdown exports written here should appear in this vault.

Developer details:

destination_type = obsidian_vault_root
export_folder = <input path resolved>
vault_root = <same as export_folder>
obsidian_config_path = <export_folder>/.obsidian
exists = true
is_directory = true
can_export = true
4.2 Inside Obsidian Vault

Condition:

export_folder exists and one of its parent folders contains .obsidian

Human result:

This folder is inside an Obsidian vault. Markdown exports should appear in the vault under this folder.

Developer details:

destination_type = inside_obsidian_vault
export_folder = <input path resolved>
vault_root = <nearest parent containing .obsidian>
obsidian_config_path = <vault_root>/.obsidian
exists = true
is_directory = true
can_export = true
4.3 Plain Markdown Folder

Condition:

export_folder exists, is a directory, and no .obsidian folder is found in the folder or its parents

Human result:

This is a normal Markdown folder. Export is allowed, but no Obsidian vault was detected.

Developer details:

destination_type = plain_markdown_folder
export_folder = <input path resolved>
vault_root = null
obsidian_config_path = null
exists = true
is_directory = true
can_export = true
4.4 Missing Folder

Condition:

export_folder does not exist

Human result:

This folder does not exist. Create the folder or choose another destination before exporting.

Developer details:

destination_type = missing_folder
export_folder = <input path resolved if possible>
vault_root = null
obsidian_config_path = null
exists = false
is_directory = false
can_export = false
4.5 Not A Directory

Condition:

export_folder exists but is not a directory

Human result:

This path is not a folder. Choose an existing folder before exporting.

Developer details:

destination_type = not_directory
export_folder = <input path resolved>
vault_root = null
obsidian_config_path = null
exists = true
is_directory = false
can_export = false
5. Human-readable Surface

The UI should show a short destination status near the export folder input.

Recommended shape:

Destination status: Obsidian vault detected
Markdown exports written here should appear in this vault.

For plain Markdown folders:

Destination status: Normal Markdown folder
Export is allowed, but no Obsidian vault was detected.

For invalid folders:

Destination status: Folder not found
Create this folder or choose another existing folder before exporting.

The human-readable surface should avoid raw enum-first messaging.

Bad:

destination_type = inside_obsidian_vault

Good:

This folder is inside an Obsidian vault.
6. Developer-readable Surface

The UI may expose technical details through a collapsible section.

Recommended label:

Show destination details

Suggested fields:

destination_type
export_folder
vault_root
obsidian_config_path
exists
is_directory
can_export
checked_at

The developer-readable surface should be available but not dominant.

It should not be the first thing a normal user sees.

7. API Shape

The implementation may use an endpoint like:

POST /documents/obsidian-export-folder-check

Request:

{
  "export_folder": "C:\\Users\\admin\\Documents\\ObsidianVault\\Inbox"
}

Response:

{
  "export_folder": "C:\\Users\\admin\\Documents\\ObsidianVault\\Inbox",
  "exists": true,
  "is_directory": true,
  "can_export": true,
  "destination_type": "inside_obsidian_vault",
  "human_status": "This folder is inside an Obsidian vault.",
  "human_next_step": "You can export Markdown here. It should appear in the detected vault.",
  "vault_root": "C:\\Users\\admin\\Documents\\ObsidianVault",
  "obsidian_config_path": "C:\\Users\\admin\\Documents\\ObsidianVault\\.obsidian",
  "checked_at": "2026-06-08T00:00:00.000000Z"
}
8. UI Placement

The destination check should appear in the Obsidian-ready Markdown Export panel.

Recommended flow:

Export folder input
-> Check destination status
-> Human-readable status card
-> Optional developer details
-> Export Markdown button

The check may run when:

the export folder input changes and is non-empty
the user clicks a Check destination button
before export submission

For the first implementation, prefer an explicit button or submit-time validation to avoid noisy checks on every keystroke.

9. Export Behavior

Plain Markdown export should remain allowed.

Obsidian detection is guidance, not a hard requirement.

Allowed:

export to Obsidian vault root
export to a folder inside an Obsidian vault
export to a normal Markdown folder

Blocked:

missing folder
path that is not a directory
unsafe path escape
overwrite existing Markdown file
10. Non-goals

This design does not include:

Obsidian plugin
Obsidian API integration
opening Obsidian
reading Obsidian settings content
modifying .obsidian
two-way sync
background watcher
automatic mass export
automatic folder creation
external LLM calls
semantic search
GitHub writeback
Result Packet write
runner, dispatcher, or watcher behavior
11. Proposed Implementation Sequence
#215 Export Destination Intelligence Core And API

Scope:

backend destination detection core
request/response schema
API route
focused tests

Expected validation:

vault root detected
inside vault detected
plain Markdown folder detected
missing folder rejected as not exportable
file path rejected as not directory
existing export behavior remains unchanged
#216 Export Destination Intelligence UI

Scope:

frontend API client
destination status card
human-readable status
collapsible developer details
export button respects non-exportable destination status

Expected validation:

web build passes
API tests pass
manual UI check shows clear human result and optional details
12. Decision

Adopt the next product step as:

Export Destination Intelligence

This keeps the product honest:

Obsidian-ready Markdown Export
-> Vault-aware destination guidance
-> still not an Obsidian plugin or sync engine

The next implementation issue should be:

#215 Export Destination Intelligence Core And API

