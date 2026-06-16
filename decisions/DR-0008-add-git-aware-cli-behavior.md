---
id: DR-0008
title: "Add Git-aware CLI behavior"
status: accepted
type: generic
stage: monitoring
date: "2026-05-10"
owner: "ahmet"
stakeholders: ["ML engineer", "supervisor"]
template_version: "1.0"
links:
  - id: "L-0001"
    rel: supported_by
    artifact_kind: document
    ref: "path:README.md"
    label: "Command overview"
    note: ""
  - id: "L-0002"
    rel: supported_by
    artifact_kind: document
    ref: "path:RUNBOOK.md"
    label: "Git-aware workflow guidance"
    note: ""
---

## Context
Decision records can reference Git commits with `git:commit:<sha>` links, but earlier CLI behavior treated those refs as plain strings only.

That made it easy to create incomplete or stale Git links and forced users to manually copy the current commit SHA when creating a decision.

## Decision
Add Git-aware CLI behavior for local repository workflows.

`dt new --git-head` resolves the current `HEAD` commit and writes a literal `git:commit:<sha>` link into the new record.

`dt validate` and `dt report` warn when a referenced `git:commit:<sha>` does not resolve to a commit object in the local Git repository.

## Rationale
Resolving `HEAD` at creation time keeps records stable and deterministic. A stored `git:HEAD` ref would change meaning as the branch moves.

Warning-only validation catches likely broken commit refs without making records non-portable across clones that may not have the same local history.

## Alternatives
1) Keep Git refs as unchecked strings
2) Allow `git:HEAD` as a persistent ref
3) Fail validation when a commit is missing locally

## Consequences
- Creating Git-linked records requires less manual SHA copying.
- Local validation can surface missing commit refs.
- Validation remains portable because Git existence checks are skipped outside Git repositories and missing commits are warnings, not failures.
