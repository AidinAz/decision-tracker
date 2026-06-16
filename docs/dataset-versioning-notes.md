# Dataset versioning notes

Evaluation results are only comparable when the dataset version is explicit. If the data changes silently, metric differences may reflect data drift rather than model or protocol changes.

Decision Records should therefore point to a concrete dataset reference when the decision depends on data. Examples include DVC hashes, checksums, or named data versions. The reference does not need to be resolved by the tool; it only needs to be stable enough for a reviewer to identify the dataset used.

The current project later supersedes the generic dataset-pinning rule by making dataset references part of the `evaluation_protocol` template. That keeps the rule closer to the decisions where missing dataset lineage would cause the most confusion.
