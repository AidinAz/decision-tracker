---
id: DR-0002
title: "Adopt Transformer encoder as baseline model"
status: accepted
type: model
stage: training
date: "2026-03-14"
owner: "ahmet"
stakeholders: ["ML engineer", "supervisor"]
template_version: "1.0"
model_spec:
  objective: "Text classification"
  model_family: "Transformer encoder"
  input: "Tokenized text"
  output: "Class label"
  primary_metric: "F1"
  acceptance_criteria: "F1 >= 0.75 on fixed eval protocol"
links:
  - id: "L-0001"
    rel: supported_by
    artifact_kind: document
    ref: "path:docs/model-selection-notes.md"
    label: "Model selection notes"
    note: ""
  - id: "L-0002"
    rel: implements
    artifact_kind: code
    ref: "git:commit:bb22cc3"
    label: "Adds transformer model module"
    note: ""
---

## Context
Existing baseline underperforms on minority classes.

## Decision
Use a Transformer encoder as the baseline architecture.

## Rationale
Better long-range dependency handling should improve minority-class performance.

## Alternatives
1) CNN text classifier
2) BiLSTM with attention

## Consequences
- Higher training cost
- More hyperparameters to tune
