---
id: DR-0007
title: "Add optional training_config to model_spec"
status: accepted
type: generic
stage: training
date: "2026-05-10"
owner: "ahmet"
stakeholders: ["ML engineer", "supervisor"]
template_version: "1.0"
links:
  - id: "L-0001"
    rel: supported_by
    artifact_kind: document
    ref: "path:RUNBOOK.md"
    label: "Model template guidance"
    note: ""
  - id: "L-0002"
    rel: supported_by
    artifact_kind: document
    ref: "path:docs/template-guidance.md"
    label: "Template guidance for training configuration"
    note: ""
---

## Context
The model template captures model selection fields such as objective, model family, input, output, primary metric, and acceptance criteria.

Training-stage decisions also need a structured place for fine-tuning and hyperparameter choices, including the tuning method, chosen values, and the rule used to select the final configuration.

## Decision
Add an optional `model_spec.training_config` block to the model template documentation and validator.

The existing required `model_spec` fields remain unchanged.

## Rationale
Keeping `training_config` optional preserves compatibility with existing accepted model decisions while giving future records machine-readable structure for training and hyperparameter rationale.

This avoids forcing fine-tuning details into free-text rationale or generic document links.

## Alternatives
1) Add a new `training` decision type
2) Rename existing `model_spec` fields such as `model_family`
3) Keep fine-tuning details only in Markdown sections

## Consequences
- Existing model records remain valid.
- Future model records can capture training configuration without changing template version semantics.
- Validation must check required `training_config` sub-fields only when the block is present.
