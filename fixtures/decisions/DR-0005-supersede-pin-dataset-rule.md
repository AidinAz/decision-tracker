---
id: DR-0005
title: "Replace generic dataset pin rule with evaluation_protocol template requirement"
status: accepted
type: generic
stage: monitoring
date: "2026-03-14"
owner: "ahmet"
stakeholders: ["ML engineer", "reviewer"]
template_version: "1.0"
links:
  - id: "L-0001"
    rel: supersedes
    artifact_kind: document
    ref: "decision:DR-0004"
    label: "Supersedes earlier rule"
    note: ""
  - id: "L-0002"
    rel: supported_by
    artifact_kind: document
    ref: "path:docs/template-guidance.md"
    label: "Template guidance"
    note: ""
---

## Context
Generic rules were not consistently applied in practice.

## Decision
Make dataset reference a mandatory field in the evaluation_protocol template.

## Rationale
Template enforcement reduces omissions compared to a separate generic rule.

## Alternatives
1) Keep DR-0004 as policy-only
2) Add a lint rule without template changes

## Consequences
- More consistent decision capture
- Slightly more upfront documentation in eval decisions
