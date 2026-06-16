---
id: DR-0009
title: "Clarify rounding and root resolution"
status: accepted
type: generic
stage: monitoring
date: "2026-06-09"
owner: "ahmet"
stakeholders: ["ML engineer", "supervisor"]
template_version: "1.0"
links:
  - id: "L-0001"
    rel: supported_by
    artifact_kind: document
    ref: "path:RUNBOOK.md"
    label: "Rounding and root behavior guidance"
    note: ""
  - id: "L-0002"
    rel: supported_by
    artifact_kind: document
    ref: "path:README.md"
    label: "Command root option overview"
    note: ""
---

## Context
The implementation originally rounded scores with a small floating-point epsilon before calling Python `round`.

The CLI also resolved paths from the shell's current directory, which made `dt validate` and `dt report` fail when run from repository subdirectories.

## Decision
Use decimal `ROUND_HALF_UP` semantics for all three-decimal score rounding.

Add `--root PATH` to `dt new`, `dt validate`, and `dt report`.

When `--root` is omitted, the CLI walks upward from the current directory and uses the first directory containing `decisions/` or `.git`.

## Rationale
Decimal rounding makes metric behavior explicit and avoids relying on an undocumented epsilon workaround.

Root discovery matches normal repository workflows, where users often run commands from nested source or documentation directories.

## Alternatives
1) Keep the epsilon-based rounding helper
2) Require all commands to be run from the repository root
3) Add only `--root` without automatic discovery

## Consequences
- Score rounding is easier to explain and reproduce.
- CLI commands work from repository subdirectories.
- Explicit `--root` remains available for scripts and tests.
