# Model selection notes

The Transformer encoder baseline was selected because the task depends on long-range text dependencies and minority-class distinctions. Simpler baselines such as CNN or BiLSTM classifiers are cheaper to train, but they provide less flexibility for representing context across longer sequences.

The decision accepts higher training cost and more hyperparameter sensitivity in exchange for a stronger baseline architecture. This is why model records can include both static model fields and an optional `training_config` block when tuning choices become part of the decision.

The baseline should be evaluated under the fixed evaluation protocol before being used for downstream threshold or deployment decisions.
