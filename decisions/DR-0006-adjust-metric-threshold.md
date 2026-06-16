---
id: DR-0006
title: "Adjust F1 acceptance threshold from 0.75 to 0.78"
status: proposed
type: evaluation_protocol
stage: evaluation
date: "2026-03-14"
owner: "ahmet"
stakeholders: ["ML engineer", "supervisor", "reviewer", "ML engineer"]
template_version: "1.0"
eval_spec:
  dataset_ref: "dvc:3f2c9a1"
  protocol: "Stratified 70/30 split, seed=42"
  metrics:
    - name: "F1"
      threshold: ">= 0.78"
  baseline:
    ref: "decision:DR-0003"
    description: "Previous threshold 0.75"
links: []
---

## Context
Recent runs suggest 0.75 is too lenient for deployment expectations.

## Decision
Propose raising the acceptance threshold to 0.78 for F1.

## Rationale
Higher threshold reduces risk of deploying underperforming models.

## Alternatives
N/A

## Consequences
- Potentially more iteration before acceptance
- Might slow deployment if improvements are hard to achieve
