---
id: DR-0003
title: "Switch evaluation to stratified 70/30 split with fixed seed"
status: accepted
type: evaluation_protocol
stage: evaluation
date: "2026-03-14"
owner: "ahmet"
stakeholders: ["ML engineer", "reviewer"]
template_version: "1.0"
eval_spec:
  dataset_ref: "dvc:3f2c9a1"
  protocol: "Stratified 70/30 split, seed=42"
  metrics:
    - name: "F1"
      threshold: ">= 0.75"
  baseline:
    ref: "decision:DR-0001"
    description: "Previous informal eval approach"
links:
  - id: "L-0001"
    rel: supported_by
    artifact_kind: data
    ref: "dvc:3f2c9a1"
    label: "Dataset version used"
    note: ""
  - id: "L-0002"
    rel: evaluated_by
    artifact_kind: experiment_run
    ref: "mlflow:run:f3a0b0d1b2c34e"
    label: "Run evaluating stratified split"
    note: ""
  - id: "L-0003"
    rel: implements
    artifact_kind: code
    ref: "git:commit:cc11dd2"
    label: "Implements stratified split"
    note: ""
---

## Context
Evaluation results were unstable due to class imbalance and small test set.

## Decision
Use stratified 70/30 split with a fixed seed (42) for dataset dvc:3f2c9a1.

## Rationale
Stabilizes metric estimates while preserving enough training data.

## Alternatives
1) 80/20 stratified split
2) k-fold cross-validation

## Consequences
- Results become comparable across runs
- Older baselines need re-running for fair comparison
