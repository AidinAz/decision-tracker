---
id: DR-0004
title: "Pin dataset version for all evaluations"
status: superseded
type: generic
stage: data
date: "2026-03-14"
owner: "ahmet"
stakeholders: ["ML engineer"]
template_version: "1.0"
links:
  - id: "L-0001"
    rel: supported_by
    artifact_kind: document
    ref: "path:docs/dataset-versioning-notes.md"
    label: "Dataset versioning notes"
    note: ""
---

## Context
Data changes over time and evaluations become non-comparable.

## Decision
Always reference a concrete dataset version/hash in evaluation decisions.

## Rationale
Prevents silent data drift during experimentation.

## Alternatives
N/A

## Consequences
- More explicit lineage
- Requires maintaining dataset versioning discipline
