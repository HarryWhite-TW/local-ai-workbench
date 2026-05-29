Away-to-Home Adoption Packets
=============================

Purpose
-------

This document defines how Away-IDE candidate work should be converted into Home Mode official adoption work.

The goal is to preserve the productivity of Away-IDE Working Mode while keeping official repository history, commit, push, and final audit rails under Home Mode control.

This document does not expand automation authority.

This document does not authorize automatic commit.

This document does not authorize automatic push.

This document does not authorize automatic issue close.

This document does not authorize full autonomous agent behavior.

Relationship to roadmap
------------------------

#114 is the roadmap anchor for Semi-automated workflow v1.

#117 defines risk levels and approval gates.

#118 defines GitHub-visible markers and readback policy.

#119 defines Away-to-Home adoption packets.

This document should be read together with the risk level, approval gate, and GitHub readback policies.

Core principle
--------------

Away-IDE Working Mode may produce candidate work.

Home Mode performs official adoption.

A candidate is not official until it is adopted, committed, pushed, and audited through the Home Mode rails.

Away-IDE completion does not approve Home Mode adoption.

Home Mode adoption does not approve commit.

Commit does not approve push.

Push does not approve issue close.

Adoption packet definition
--------------------------

An adoption packet is a structured handoff from Away-IDE candidate work to Home Mode official adoption.

The packet should contain enough information for Home Mode to recreate or apply the accepted candidate safely.

An adoption packet should not require trusting the dirty Away-IDE workspace.

An adoption packet should not require carrying over unreviewed files.

An adoption packet should not automatically trigger commit or push.

Packet purpose
--------------

The adoption packet exists to answer:

* what logical issue is being adopted
* what candidate was accepted
* what file should be created or updated
* what content should be written
* what base commit is expected
* what operations are allowed
* what operations are forbidden
* what evidence should be produced
* what the next approval gate is

Required packet fields
----------------------

A Home Mode adoption packet should include:

* logical issue number
* source marker or review evidence
* target repository
* expected branch
* expected base commit
* expected origin/master
* allowed file path
* forbidden file paths
* exact document content or exact patch source
* expected audit checks
* expected GitHub marker
* next recommended action
* explicit non-goals

The packet should be written so Codex can execute it without guessing.

Source evidence
---------------

The packet should reference candidate evidence.

Acceptable candidate evidence includes:

* ReviewBundle marker
* candidate audit marker
* GitHub issue comment
* short structured user-provided audit block
* ChatGPT-reviewed candidate content

For official adoption, marker-only evidence is acceptable only when the adopted content is explicitly provided in the Home Mode prompt.

Home Mode should not pull content from an uncontrolled dirty candidate folder.

Base state requirement
----------------------

Home Mode adoption must start from a known base state.

Before applying a packet, Codex should verify:

* repository full name
* current branch
* HEAD
* origin/master
* latest commit message
* working tree clean
* no staged changes
* no pending candidate dirty files

If any base state check fails, Codex must stop.

One issue at a time
-------------------

Home Mode adoption should process one logical issue at a time.

One packet should correspond to one logical issue.

One ReviewBundle should correspond to one logical issue.

One commit should correspond to one logical issue unless a future prompt explicitly scopes otherwise.

Batch adoption is forbidden by default.

One file at a time by default
-----------------------------

Each adoption packet should modify one primary file by default.

Multiple files require explicit scope, stronger review, and a separate reason.

For the current Semi-automated workflow v1 adoption sequence, each logical issue should use one docs-only file unless separately approved.

Allowed Home Mode adoption actions
----------------------------------

During the Home Mode official apply and ReviewBundle phase, allowed actions are:

* inspect current repository state
* create or update exactly the allowed docs file
* run read-only diff checks
* verify changed file list
* verify no staged changes
* verify no commit occurred
* verify no push occurred
* write ReviewBundle marker to the scoped GitHub issue
* stop for ChatGPT review

Forbidden Home Mode adoption actions
------------------------------------

During the Home Mode official apply and ReviewBundle phase, forbidden actions are:

* stage
* commit
* push
* pull
* merge
* rebase
* reset
* restore
* clean
* branch creation
* branch switching
* PR creation
* PR merge
* issue close
* issue reopen
* label change
* assignee change
* runner execution
* dispatcher execution
* pytest execution
* runtime smoke execution
* adoption of unrelated logical issues
* approval chaining

Commit phase separation
-----------------------

Home Mode adoption does not include commit approval.

After ReviewBundle success, ChatGPT must review the result.

The user must explicitly approve the commit phase.

The commit phase must stage only the approved file.

The commit phase must create exactly one local commit.

The commit phase must stop before push.

Push phase separation
---------------------

Commit approval does not include push approval.

After local commit audit success, ChatGPT must review the result.

The user must explicitly approve the push phase.

The push phase must push exactly the approved commit to the expected remote branch.

The push phase must not create new commits or modify files.

Final audit separation
----------------------

Push approval does not include final audit approval by itself.

After push, the workflow should perform a final read-only audit.

The final audit should confirm:

* remote commit exists
* remote file exists
* HEAD equals origin/master
* working tree clean
* no staged changes
* no PR created
* no merge performed
* no issue closed
* runtime behavior unchanged
* runner behavior unchanged
* dispatcher behavior unchanged
* automation authority not expanded

Adoption packet success criteria
--------------------------------

A Home Mode adoption packet succeeds when:

* only the allowed file changes
* changed files count is correct
* git diff check passes
* no fenced code blocks are present when forbidden by the document policy
* no staged changes exist
* no commit occurs during ReviewBundle phase
* no push occurs during ReviewBundle phase
* ReviewBundle marker is written
* ChatGPT can review the result

Commit success criteria
-----------------------

A commit phase succeeds when:

* exactly one local commit is created
* commit message matches expected
* committed files match expected
* working tree is clean
* no staged changes remain
* no push occurs
* no PR is created
* no issue is closed

Push success criteria
---------------------

A push phase succeeds when:

* approved commit is pushed to expected remote branch
* remote master or expected branch points to the approved commit
* no new commit is created during push phase
* no file modification occurs during push phase
* no PR is created
* no merge occurs
* no issue is closed

Final audit success criteria
----------------------------

A final audit succeeds when:

* expected commit is visible remotely
* expected file is visible remotely
* expected content can be read
* no unauthorized file is present
* no PR is created
* no merge occurs
* no issue is closed
* no runtime behavior changes
* no runner behavior changes
* no dispatcher behavior changes
* no automation authority expansion occurs

Candidate contamination rule
----------------------------

Candidate contamination exists when a working tree contains files from another logical issue.

If candidate contamination is detected during Home Mode adoption, Codex must stop.

Codex must not automatically repair contamination.

Codex must not reset, restore, clean, or remove files without a separate recovery approval.

Away-IDE folder rule
--------------------

Away-IDE candidate folders should not be reused for Home Mode official adoption.

Home Mode should use the primary clean local repo.

If the user returns from Away-IDE work, Home Mode should begin with a recovery audit before applying a packet.

Exact content rule
------------------

For docs-only adoption, the safest packet form is exact content replacement.

The prompt should include BEGIN_DOCUMENT and END_DOCUMENT boundaries.

Codex should write only the content between those boundaries.

Codex should not write instructions, checks, or prompt metadata into the document.

Marker rule
-----------

Adoption packets should specify the required ReviewBundle marker.

The marker should include:

* protocol
* issue_source
* logical_issue
* result
* phase
* working_mode
* branch
* base_head
* changed_files
* changed_files_count
* docs_only
* safety confirmations
* next recommended action

A marker is evidence for ChatGPT review.

A marker is not approval for the next high-risk phase.

Stop conditions
---------------

Codex must stop when:

* repo is wrong
* branch is wrong
* HEAD is wrong
* origin/master is wrong
* working tree is unexpectedly dirty
* staged changes already exist
* changed files are unexpected
* candidate contamination is detected
* git diff check fails
* required content cannot be applied exactly
* marker cannot be posted
* forbidden operation would be needed
* high-risk approval is missing

Stopping is a successful safety behavior.

Recovery rule
-------------

Recovery requires a separate review.

Codex must not automatically recover by:

* reset
* restore
* clean
* pull
* merge
* rebase
* branch recreation
* replacement commit
* push retry
* force push
* issue close
* label change

If recovery may touch repository state, it requires explicit user approval.

Non-goals
---------

This document does not authorize:

* automatic adoption
* automatic commit
* automatic push
* automatic issue close
* automatic PR creation
* automatic merge
* approval chaining
* batch adoption
* unrestricted Codex execution
* background watcher
* always-on polling
* full autonomous agent behavior
* Lv5 full automation
* expanding Away-IDE Git write authority
* changing runner behavior
* changing dispatcher behavior
* changing runtime behavior

Current status
--------------

This document defines Away-to-Home adoption packets for Semi-automated workflow v1.

It supports the current ChatGPT-centered Lv4.5-style workflow.

It does not implement new dispatcher behavior.

It does not change runtime behavior.

It does not change runner behavior.

It does not change dispatcher behavior.

It does not expand automation authority.

Future changes to adoption packet authority or automation scope require separate design, review, and explicit approval.
