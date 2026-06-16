# Template guidance

Decision Tracker has three decision types: `generic`, `model`, and `evaluation_protocol`.

Use `generic` for process, policy, dataset, or project decisions that do not need specialized structured fields.

Use `model` when the decision is about model selection, model definition, or training configuration. The required `model_spec` fields describe what the model is and how it will be judged. The optional `model_spec.training_config` block describes how the model was trained or tuned.

Example:

```yaml
model_spec:
  objective: "Text classification"
  model_family: "Transformer encoder"
  input: "Tokenized text"
  output: "Class label"
  primary_metric: "F1"
  acceptance_criteria: "F1 >= 0.75 on fixed eval protocol"
  training_config:
    tuning_method: "random_search"
    selected_hyperparameters:
      learning_rate: "3e-5"
      batch_size: "16"
    selection_rule: "Choose highest validation F1"
```

Use `evaluation_protocol` when the decision is about how models are evaluated: dataset version, split protocol, metrics, thresholds, and baseline comparison.
