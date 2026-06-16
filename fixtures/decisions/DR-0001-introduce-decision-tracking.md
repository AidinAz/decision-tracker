---
id: DR-0001
title: "Introduce decision tracking artifacts in repo"
status: accepted
type: generic
stage: monitoring
date: "2026-03-14"
owner: "ahmet"
stakeholders: ["ML engineer", "reviewer"]
template_version: "1.0"
links:
  - id: "L-0001"
    rel: supported_by
    artifact_kind: document
    ref: "path:docs/decision-tracking-rationale.md"
    label: "Rationale doc"
    note: ""
---

## Context
Decisions and rationale are scattered across commits and chats.

## Decision
Store Decision Records (DRs) as Markdown + YAML in the repository.

## Rationale
Git-native artifacts reduce friction and improve traceability.

## Alternatives
N/A

## Consequences
- Better auditability and reproducibility
- Requires discipline to keep records updated
