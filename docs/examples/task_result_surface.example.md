Task and Result Surface v1 Example

Purpose

This file provides examples for Task Surface and Result Surface v1.

These examples are documentation only.

These examples do not authorize implementation.

These examples do not authorize runner code.

These examples do not authorize automatic commit.

These examples do not authorize automatic push.

These examples do not authorize automatic issue close.

These examples do not authorize background watcher behavior.

These examples do not authorize Lv5 full automation.

These examples do not create real task surfaces.

These examples do not create real result surfaces.

Example 1: preferred task-specific GitHub surfaces

roadmap_anchor:
  role: roadmap_anchor
  kind: github_issue
  url: "https://github.com/HarryWhite-TW/local-ai-workbench/issues/114"
  issue: 114
  comment_id: null
  path: null
  sha: null
  active_packet_count: 0
  fallback: false
  fallback_reason: null
task_surface:
  role: task_surface
  kind: github_comment
  url: "https://github.com/HarryWhite-TW/local-ai-workbench/issues/128#issuecomment-0000000001"
  issue: 128
  comment_id: 1
  path: null
  sha: null
  active_packet_count: 1
  fallback: false
  fallback_reason: null
result_surface:
  role: result_surface
  kind: github_comment
  url: "https://github.com/HarryWhite-TW/local-ai-workbench/issues/128#issuecomment-0000000002"
  issue: 128
  comment_id: 2
  path: null
  sha: null
  active_packet_count: 1
  fallback: false
  fallback_reason: null

This is the preferred v1 topology.

The roadmap anchor remains visible but does not contain the full task or result packet.

The task and result surfaces are task-specific and short.

Example 2: transitional #114 marker with canonical result pointer

roadmap_anchor_marker:
  role: roadmap_anchor
  kind: github_comment
  url: "https://github.com/HarryWhite-TW/local-ai-workbench/issues/114#issuecomment-0000000003"
  issue: 114
  comment_id: 3
  path: null
  sha: null
  active_packet_count: 0
  fallback: false
  fallback_reason: null
  points_to:
    task_surface_url: "https://github.com/HarryWhite-TW/local-ai-workbench/issues/128#issuecomment-0000000001"
    result_surface_url: "https://github.com/HarryWhite-TW/local-ai-workbench/issues/128#issuecomment-0000000002"

This keeps #114 useful as a roadmap anchor.

It avoids using #114 as the primary long-term result packet sink.

Example 3: local file fallback during implementation

task_surface:
  role: task_surface
  kind: local_file
  url: null
  issue: null
  comment_id: null
  path: "docs/tasks/task-128.example.md"
  sha: null
  active_packet_count: 1
  fallback: true
  fallback_reason: "github_task_surface_not_yet_available"
result_surface:
  role: result_surface
  kind: local_file
  url: null
  issue: null
  comment_id: null
  path: "docs/results/result-128.example.md"
  sha: null
  active_packet_count: 1
  fallback: true
  fallback_reason: "github_result_surface_not_yet_available"

This is fallback.

It is not target bridge success.

The result packet must include remaining_bridge_gaps.

Example 4: invalid surface with multiple active packets

result_surface:
  role: result_surface
  kind: github_comment
  url: "https://github.com/HarryWhite-TW/local-ai-workbench/issues/128#issuecomment-0000000004"
  issue: 128
  comment_id: 4
  path: null
  sha: null
  active_packet_count: 2
  fallback: false
  fallback_reason: null
validation:
  expected_result: failure
  failure_reason: "multiple_active_result_packets"

The reader must fail closed.

A surface must not contain multiple active result packets.

Example 5: invalid fallback without fallback reason

result_surface:
  role: result_surface
  kind: local_stdout
  url: null
  issue: null
  comment_id: null
  path: null
  sha: null
  active_packet_count: 1
  fallback: true
  fallback_reason: null
validation:
  expected_result: failure
  failure_reason: "fallback_reason_required"

Fallback must be explicit.

Fallback must include a reason.

Example 6: invalid roadmap issue as primary result sink

result_surface:
  role: result_surface
  kind: github_issue
  url: "https://github.com/HarryWhite-TW/local-ai-workbench/issues/114"
  issue: 114
  comment_id: null
  path: null
  sha: null
  active_packet_count: 1
  fallback: false
  fallback_reason: null
validation:
  expected_result: failure
  failure_reason: "roadmap_anchor_used_as_primary_result_surface_without_fallback_permission"

A long-lived roadmap issue should not be used as the primary result packet sink.

If it is used during transition, it must be labeled fallback or pointer-only.

Safety notes

These examples are schema examples.

They are not active task surfaces.

They are not active result surfaces.

A surface is a location and binding model.

A surface is not approval.

A result surface stores evidence.

A result surface does not approve commit.

A result surface does not approve push.

A result surface does not approve issue close.

High-risk phases still require explicit user approval through ChatGPT.

Manual fallback must remain labeled.

Manual foreground start must remain labeled as transitional when applicable.

Task and result copy/paste should be reduced by the bridge.

Task and Result Surface v1 does not authorize Lv5 full automation.
