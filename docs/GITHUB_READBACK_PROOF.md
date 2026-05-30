GitHub Readback Proof
Purpose

This document records the proof that ChatGPT can review GitHub-visible workflow results without requiring the user to paste long Codex output.

The goal is to reduce manual relay work while preserving auditability, user control, and safety gates.

This document does not expand automation authority.

This document does not authorize automatic commit.

This document does not authorize automatic push.

This document does not authorize automatic issue close.

This document does not authorize full autonomous agent behavior.

Relationship to roadmap

#114 is the roadmap anchor for Semi-automated workflow v1.

#117 defines risk levels and approval gates.

#118 defines GitHub-visible markers and readback policy.

#119 defines Away-to-Home adoption packets.

#120 proves that ChatGPT can read back GitHub-visible results directly.

This document should be read together with the marker and readback policy.

Proof target

The proof target is simple:

The user should not need to paste the full Codex transcript into ChatGPT.

Instead, the user should be able to say that the task is complete.

ChatGPT should then read GitHub-visible evidence directly from the scoped issue, commit, or remote file.

Verified readback surfaces

The following GitHub-visible surfaces are valid readback targets:

GitHub issue comments
structured marker comments
commit search results
remote commits
remote files
branch state when explicitly checked
issue state when explicitly checked

These surfaces are useful because they are shared, auditable, and reviewable.

Marker readback proof

ChatGPT has repeatedly used GitHub issue #114 to find structured markers.

Examples of marker families used in the workflow include:

REVIEWBUNDLE-AUDIT-VISIBLE
LOCAL-COMMIT-AUDIT-VISIBLE
PUSH-AUDIT-VISIBLE
FINAL-AUDIT-VISIBLE

These markers allow ChatGPT to determine whether a scoped phase succeeded, failed, stopped, or requires repair.

A marker is evidence for review.

A marker is not authority by itself.

Commit readback proof

ChatGPT can search for expected commit messages and confirm that a commit exists on GitHub.

Commit readback is stronger than local-only evidence because it verifies a remote GitHub-visible state.

Commit readback should include:

commit SHA
commit message
repository identity
changed file expectations when available

Commit readback does not replace content readback when file content matters.

Remote file readback proof

ChatGPT can fetch a remote file from GitHub and inspect the actual content.

Remote file readback is stronger than marker-only evidence when the acceptance criteria depend on exact file content.

Remote file readback should be preferred when checking:

file existence
title or heading format
required sections
required policy language
exact first-line content
absence of forbidden claims
Readback conflict proof

The workflow has already demonstrated that marker evidence alone is not enough.

A push marker may say success, while remote file readback may still reveal a formatting issue.

When marker evidence and remote readback disagree, remote readback wins.

The correct behavior is to stop, diagnose, and repair through a separate scoped task.

This is a successful safety behavior, not a workflow failure.

User relay reduction

The user no longer needs to paste the entire Codex transcript for every step.

A short completion message such as the following is enough when GitHub markers are available:

ReviewBundle complete, please audit GitHub issue
local commit complete, please audit GitHub issue
push complete, please audit GitHub issue
final audit complete, please audit GitHub issue

The user may still paste a short structured audit block as a fallback when GitHub readback fails.

Fallback rule

GitHub-visible readback is preferred.

Fallback paste remains allowed when:

marker search is delayed
marker search is ambiguous
connector readback is unavailable
local-only state must be reviewed before push
the expected GitHub evidence is missing

Fallback paste should be short and structured.

The fallback should not be a full long transcript unless specifically needed for diagnosis.

Safety boundaries

GitHub readback does not authorize:

automatic commit
automatic push
automatic issue close
automatic PR creation
automatic merge
approval chaining
broad issue scanning
background watcher behavior
always-on polling
unrestricted Codex execution
full autonomous agent behavior
Lv5 full automation

Readback is evidence collection.

Readback is not execution authority.

Approval gates remain separate

Successful readback does not approve the next high-risk phase.

ReviewBundle success does not approve commit.

Local commit audit success does not approve push.

Push audit success does not approve issue close.

Final audit success does not approve the next roadmap task by itself.

High-risk actions still require explicit user approval.

Success criteria

The GitHub readback proof is considered successful when:

ChatGPT can find the expected marker on GitHub
ChatGPT can identify the target issue
ChatGPT can search for the expected commit when needed
ChatGPT can fetch the expected remote file when needed
ChatGPT can detect conflict between marker evidence and file content
ChatGPT can stop instead of accepting weak evidence
the user does not need to paste the full Codex transcript
high-risk approval gates remain intact
Current status

This document records the GitHub readback proof for Semi-automated workflow v1.

It supports the current ChatGPT-centered Lv4.5-style workflow.

It does not implement new dispatcher behavior.

It does not change runtime behavior.

It does not change runner behavior.

It does not change dispatcher behavior.

It does not expand automation authority.

Future changes to readback authority, automation scope, or background execution require separate design, review, and explicit approval.
