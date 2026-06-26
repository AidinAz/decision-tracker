from __future__ import annotations

import re

STATUSES = {"proposed", "accepted", "rejected", "superseded", "deprecated"}
TYPES = {"model", "evaluation_protocol", "generic"}
STAGES = {"data", "training", "evaluation", "deployment", "monitoring"}
RELS = {"implements", "evaluated_by", "supported_by", "supersedes"}
ARTIFACT_KINDS = {"code", "data", "experiment_run", "document", "issue"}
REQUIRED_HEADINGS = ["Context", "Decision", "Rationale", "Alternatives", "Consequences"]
CORE_HEADINGS = ["Context", "Decision", "Rationale", "Consequences"]
ID_RE = re.compile(r"^DR-\d{4}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DISCOVER_KEYWORDS = (
    "adopt",
    "choose",
    "switch",
    "replace",
    "pin",
    "threshold",
    "metric",
    "baseline",
    "dataset",
    "evaluation",
    "fine-tune",
    "hyperparameter",
)
RECONSTRUCTION_CONFIDENCE = {"low", "medium", "high"}
GIT_SUBPROCESS_TIMEOUT = 5

REF_PATTERNS = [
    re.compile(r"^git:commit:[A-Za-z0-9]+$"),
    re.compile(r"^git:ref:.+$"),
    re.compile(r"^github:pr:\d+$"),
    re.compile(r"^github:issue:\d+$"),
    re.compile(r"^url:https://.+$"),
    re.compile(r"^dvc:.+$"),
    re.compile(r"^checksum:sha256:.+$"),
    re.compile(r"^data:version:.+$"),
    re.compile(r"^mlflow:run:.+$"),
    re.compile(r"^wandb:run:.+$"),
    re.compile(r"^run:.+$"),
    re.compile(r"^path:.+$"),
    re.compile(r"^decision:DR-\d{4}$"),
]
