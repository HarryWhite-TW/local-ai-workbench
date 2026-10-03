# AGENTS.md

## Scope

These rules automatically govern work under `src/local_runner_bridge/`.

Root `AGENTS.md` continues to govern repository-wide safety. If these scoped
rules are more specific for bridge work, follow them within this folder.

Root `AGENTS.md` also requires tasks using or changing the incumbent Bridge,
Dispatcher, Runner, Task Packet, or Bridge Operator in other paths to use this
file as the bridge-specific governance reference. Native Codex execution alone
does not select this route; work on files in this folder still follows these rules.

This file cannot weaken root repository-wide safety.

## Governing Authorities

- `docs/CHATGPT_CODEX_BRIDGE_DIRECTION_LOCK.md` governs bridge direction.
- `docs/BRIDGE_OPERATOR_V0_SPEC.md` governs Bridge Operator design and authority.
- Root `AGENTS.md` governs repository-wide safety, product positioning, and general collaboration rules.

## Current Direction

- ChatGPT remains the primary user interface.
- Ordinary local engineering follows root `AGENTS.md`'s Native-first Work route
  when native capabilities satisfy the task. Independent ChatGPT final technical
  review of the exact candidate, diff, and evidence against the approved task is
  required; executor completion is not acceptance.
- When ChatGPT Work is the execution surface, same-conversation review is
  preferred to avoid manual relay, not a permanent architectural requirement.
  Supervising ChatGPT or a future Companion/control surface may perform that
  independent final review. The user must not become the routine technical
  relay between execution and review.
- Bridge / Operator / Dispatcher / Runner remains specialised governance,
  compatibility, recovery, or fallback infrastructure, not mandatory transport
  for ordinary engineering. Its governing authorities above continue to apply
  when using or changing this route.
- For the Bridge route, GitHub remains the auditable task and result surface;
  this does not require GitHub mutation for every native local task.
- Manual copy/paste and manual `PollOnce` are Bridge fallback or recovery paths,
  not a requirement that the user relay ordinary engineering prompts or results.
- Current Roadmap sequencing and the active or next node must come from the applicable current plan and active task, tracker, or node source when the work actually requires a sequencing, activation, closeout, or authority decision.
- This scoped rule file does not own, freeze, or activate the current or next Roadmap phase or node.

## Authority Hierarchy

Current normative documents override:

- historical Issue discussions;
- old Task Packets;
- smoke evidence;
- validation plans;
- decision notes;
- superseded roadmaps.

Historical evidence may explain how a decision was reached, but it must not
silently create a new current requirement.

## Bridge Task Sizing

- A bounded vertical slice may modify multiple explicitly approved bridge modules and include the implementation, test, repair, and evidence steps required for one end-to-end outcome.
- Do not split an integrated outcome solely to satisfy an arbitrary file-count or technical-step limit.
- File count alone is not the risk model.
- Risk is determined by authority, side effects, external access, persistence, execution scope, and recovery behavior.
- Stop for a separate approval when the work would materially expand the approved objective, authority, side effects, or scope, not merely because the bounded outcome spans several files or steps.
- Architecture audits may read the complete explicitly scoped bridge folder.

## Preserved Prohibitions

Continue to forbid:

- broad Issue scanning;
- latest or next Issue inference;
- automatic commit or push;
- automatic Issue closure or label changes;
- PR creation or merge;
- approval consumption or chaining;
- hidden unattended services;
- unauthorized startup behavior;
- trusted-actor changes;
- unrelated product-runtime modifications;
- scope expansion outside explicitly allowed paths.

Implementation work always requires a separately approved task.
