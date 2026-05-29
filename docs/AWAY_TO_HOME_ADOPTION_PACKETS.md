Away-to-Home Adoption Packets

## Purpose

This document defines how Away-IDE candidate work should be converted into Home Mode official adoption work.

The goal is to preserve the productivity of Away-IDE Working Mode while keeping official repository history, commit, push, and final audit rails under Home Mode control.

This document does not expand automation authority.

This document does not authorize automatic commit.

This document does not authorize automatic push.

This document does not authorize automatic issue close.

This document does not authorize full autonomous agent behavior.

## Relationship to roadmap

#114 is the roadmap anchor for Semi-automated workflow v1.

#117 defines risk levels and approval gates.

#118 defines GitHub-visible markers and readback policy.

#119 defines Away-to-Home adoption packets.

This document should be read together with the risk level, approval gate, and GitHub readback policies.

## Core principle

Away-IDE Working Mode may produce candidate work.

Home Mode performs official adoption.

A candidate is not official until it is adopted, committed, pushed, and audited through the Home Mode rails.

Away-IDE completion does not approve Home Mode adoption.

Home Mode adoption does not approve commit.

Commit does not approve push.

Push does not approve issue close.

## Adoption packet definition

An adoption packet is a structured handoff from Away-IDE candidate work to Home Mode official adoption.

The packet should contain enough information for Home Mode to recreate or apply the accepted candidate safely.

An adoption packet should not require trusting the dirty Away-IDE workspace.

An adoption packet should not require carrying over unreviewed files.

An adoption packet should not automatically trigger commit or push.

## Packet purpose

The adoption packet exists to answer:

- what logical issue is being adopted
- what candidate was accepted
- what file should be created or updated
- what content should be written
- what base commit is expected
- what operations are allowed
- what operations are forbidden
- what evidence should be produced
- what the next approval gate is

## Required packet fields

A Home Mode adoption packet should include:

- logical issue number
- source marker or review evidence
- target repository
- expected branch
- expected base commit
- expected origin/master
- allowed file path
- forbidden file paths
- exact document content or exact patch source
- expected audit checks
- expected GitHub marker
- next recommended action
- explicit non-goals

The packet should be written so Codex can execute it without guessing.

## Source evidence

The packet should reference candidate evidence.

Acceptable candidate evidence includes:

- ReviewBundle marker
- candidate audit marker
- GitHub issue comment
- short structured user-provided audit block
- ChatGPT-reviewed candidate content

For official adoption, marker-only evidence is acceptable only when the adopted content is explicitly provided in the Home Mode prompt.

Home Mode should not pull content from an uncontrolled dirty candidate folder.

## Base state requirement

Home Mode adoption must start from a known base state.

Before applying a packet, Codex should verify:

- repository full name
- current branch
- HEAD
- origin/master
- latest commit message
- working tree clean
- no staged changes
- no pending candidate dirty files

If any base state check fails, Codex must stop.

## One issue at a time

Home Mode adoption should process one logical issue at a time.

One packet should correspond to one logical issue.

One ReviewBundle should correspond to one logical issue.

One commit should correspond to one logical issue unless a future prompt explicitly scopes otherwise.

Batch adoption is forbidden by default.

## One file at a time by default

Each adoption packet should modify one primary file by default.

Multiple files require explicit scope, stronger review, and a separate reason.

For the current Semi-automated workflow v1 adoption sequence, each logical issue should use one docs-only file unless separately approved.

## Current status

This document defines Away-to-Home adoption packets for Semi-automated workflow v1.

It supports the current ChatGPT-centered Lv4.5-style workflow.

It does not implement new dispatcher behavior.

It does not change runtime behavior.

It does not change runner behavior.

It does not change dispatcher behavior.

It does not expand automation authority.

Future changes to adoption packet authority or automation scope require separate design, review, and explicit approval.
