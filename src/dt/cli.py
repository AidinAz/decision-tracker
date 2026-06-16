from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Optional

import typer
import yaml

app = typer.Typer(help="Decision Tracker CLI")

STATUSES = {"proposed", "accepted", "rejected", "superseded", "deprecated"}
TYPES = {"model", "evaluation_protocol", "generic"}
STAGES = {"data", "training", "evaluation", "deployment", "monitoring"}
RELS = {"implements", "evaluated_by", "supported_by", "supersedes"}
ARTIFACT_KINDS = {"code", "data", "experiment_run", "document", "issue"}
REQUIRED_HEADINGS = ["Context", "Decision", "Rationale", "Alternatives", "Consequences"]
CORE_HEADINGS = ["Context", "Decision", "Rationale", "Consequences"]
ID_RE = re.compile(r"^DR-\d{4}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

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


@dataclass
class ValidationMessage:
    code: str
    message: str


@dataclass
class LoadedRecord:
    path: Path
    yaml_id: str
    doc: Optional[dict[str, Any]] = None
    headings: dict[str, str] = field(default_factory=dict)
    heading_counts: dict[str, int] = field(default_factory=dict)
    parse_errors: list[ValidationMessage] = field(default_factory=list)


@dataclass
class DecisionComputed:
    raw: dict[str, Any]
    links_sorted: list[dict[str, Any]]
    headings: dict[str, str]
    stakeholders: list[str]
    has_minimum_trace_links: int
    score_completeness: float
    score_connectedness: float
    score_inclusiveness: float
    score_traceability: float
    rel_counts: dict[str, int]
    unique_artifacts_by_kind: dict[str, int]
    unique_artifacts_total: int
    unique_decision_targets_total: int
    alternatives_is_na: int


@dataclass
class ValidationContext:
    incoming_supersedes: dict[str, int]
    all_ids: set[str]
    duplicate_ids: set[str]


def _round3(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))


def _discover_project_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "decisions").exists() or (candidate / ".git").exists():
            return candidate
    return start


def _resolve_root(root: Optional[Path]) -> Path:
    if root is not None:
        return root.resolve()
    return _discover_project_root(Path.cwd().resolve())


def _json_dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_text(rendered, encoding="utf-8")


def _ref_is_valid(ref: Any) -> bool:
    if not isinstance(ref, str) or not ref.strip():
        return False
    return any(pattern.match(ref) for pattern in REF_PATTERNS)


def _infer_target_id(ref: str) -> str:
    if ref.startswith("decision:"):
        return ref
    digest = hashlib.sha256(ref.encode("utf-8")).hexdigest()
    return f"artifact:{digest}"


def _git_repo_root(root: Path) -> Optional[Path]:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip()).resolve()


def _resolve_git_head(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("git executable was not found") from exc
    except subprocess.SubprocessError as exc:
        raise RuntimeError("git command failed while resolving HEAD") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or "not a Git repository or HEAD does not exist"
        raise RuntimeError(detail)
    return result.stdout.strip()


def _git_commit_exists(root: Path, sha: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "cat-file", "-e", f"{sha}^{{commit}}"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return True
    return result.returncode == 0


def _extract_front_matter(content: str) -> tuple[str, str]:
    if not content.startswith("---\n"):
        raise ValueError("Missing front matter start")
    parts = content.split("\n---\n", 1)
    if len(parts) != 2:
        raise ValueError("Missing front matter end")
    return parts[0][4:], parts[1]


def _heading_counts(markdown_body: str) -> dict[str, int]:
    counts = {name: 0 for name in REQUIRED_HEADINGS}
    for line in markdown_body.splitlines():
        if line.startswith("## "):
            heading = line[3:].strip()
            if heading in counts:
                counts[heading] += 1
    return counts


def _parse_headings(markdown_body: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: Optional[str] = None
    for line in markdown_body.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(line)
    return {name: "\n".join(lines).strip() for name, lines in sections.items()}


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_non_empty_mapping(value: Any) -> bool:
    return isinstance(value, dict) and bool(value)


def _is_non_empty_section(value: Optional[str]) -> bool:
    return bool(value and value.strip())


def _stable_stakeholders(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    dedup: dict[str, str] = {}
    for raw in values:
        if not isinstance(raw, str):
            continue
        clean = raw.strip()
        if not clean:
            continue
        key = clean.lower()
        if key not in dedup:
            dedup[key] = clean
    return sorted(dedup.values(), key=lambda v: v.lower(), reverse=True)


def _stakeholder_duplicate_warnings(values: Any) -> list[ValidationMessage]:
    if not isinstance(values, list):
        return []
    seen: dict[str, str] = {}
    warnings: list[ValidationMessage] = []
    for raw in values:
        if not isinstance(raw, str):
            continue
        clean = raw.strip()
        if not clean:
            continue
        key = clean.lower()
        if key in seen:
            warnings.append(
                ValidationMessage(
                    "STAKEHOLDER_DUPLICATE",
                    f"Duplicate stakeholder ignored for metrics: {clean}",
                )
            )
        else:
            seen[key] = clean
    return warnings


def _parse_stakeholders_csv(raw: str) -> list[str]:
    if not raw.strip():
        return []
    dedup: dict[str, str] = {}
    for piece in raw.split(","):
        clean = piece.strip()
        if not clean:
            continue
        key = clean.lower()
        if key not in dedup:
            dedup[key] = clean
    return list(dedup.values())


def _slugify_title(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "untitled"


def _next_decision_id(decisions_dir: Path) -> str:
    max_id = 0
    for path in sorted(decisions_dir.glob("DR-*.md"), key=lambda p: p.name):
        candidate: Optional[str] = None
        try:
            text = path.read_text(encoding="utf-8")
            yaml_text, _ = _extract_front_matter(text)
            doc = yaml.safe_load(yaml_text)
            if isinstance(doc, dict) and isinstance(doc.get("id"), str) and ID_RE.match(doc["id"]):
                candidate = doc["id"]
        except (ValueError, yaml.YAMLError):
            candidate = None
        if candidate is None:
            match = re.match(r"^(DR-\d{4})", path.stem)
            if match:
                candidate = match.group(1)
        if candidate is not None:
            max_id = max(max_id, int(candidate.split("-")[1]))
    return f"DR-{max_id + 1:04d}"


def _template_payload(decision_type: str) -> dict[str, Any]:
    if decision_type == "model":
        return {
            "model_spec": {
                "objective": "TODO",
                "model_family": "TODO",
                "input": "TODO",
                "output": "TODO",
                "primary_metric": "TODO",
                "acceptance_criteria": "TODO",
            }
        }
    if decision_type == "evaluation_protocol":
        return {
            "eval_spec": {
                "dataset_ref": "data:version:TODO",
                "protocol": "TODO",
                "metrics": [{"name": "TODO", "threshold": "TODO"}],
                "baseline": {
                    "ref": "run:TODO",
                    "description": "TODO",
                },
            }
        }
    return {}


def _template_validation_errors(doc: dict[str, Any]) -> list[ValidationMessage]:
    errors: list[ValidationMessage] = []
    decision_type = doc.get("type")

    if decision_type == "model":
        spec = doc.get("model_spec")
        if not isinstance(spec, dict):
            errors.append(ValidationMessage("TEMPLATE_FIELD_MISSING", "Missing object: model_spec"))
            return errors
        for field_name in (
            "objective",
            "model_family",
            "input",
            "output",
            "primary_metric",
            "acceptance_criteria",
        ):
            if not _is_non_empty_string(spec.get(field_name)):
                errors.append(
                    ValidationMessage(
                        "TEMPLATE_FIELD_MISSING",
                        f"model_spec.{field_name} must be a non-empty string",
                    )
                )
        training_config = spec.get("training_config")
        if training_config is not None:
            if not isinstance(training_config, dict):
                errors.append(
                    ValidationMessage(
                        "TEMPLATE_FIELD_MISSING",
                        "model_spec.training_config must be an object when present",
                    )
                )
            else:
                for field_name in ("tuning_method", "selection_rule"):
                    if not _is_non_empty_string(training_config.get(field_name)):
                        errors.append(
                            ValidationMessage(
                                "TEMPLATE_FIELD_MISSING",
                                f"model_spec.training_config.{field_name} must be a non-empty string",
                            )
                        )
                if not _is_non_empty_mapping(training_config.get("selected_hyperparameters")):
                    errors.append(
                        ValidationMessage(
                            "TEMPLATE_FIELD_MISSING",
                            "model_spec.training_config.selected_hyperparameters must be a non-empty object",
                        )
                    )
                for field_name in ("stopping_rule", "compute_environment"):
                    value = training_config.get(field_name)
                    if value is not None and not _is_non_empty_string(value):
                        errors.append(
                            ValidationMessage(
                                "TEMPLATE_FIELD_MISSING",
                                f"model_spec.training_config.{field_name} must be a non-empty string when present",
                            )
                        )
                search_space = training_config.get("search_space")
                if search_space is not None and not _is_non_empty_mapping(search_space):
                    errors.append(
                        ValidationMessage(
                            "TEMPLATE_FIELD_MISSING",
                            "model_spec.training_config.search_space must be a non-empty object when present",
                        )
                    )

    if decision_type == "evaluation_protocol":
        spec = doc.get("eval_spec")
        if not isinstance(spec, dict):
            errors.append(ValidationMessage("TEMPLATE_FIELD_MISSING", "Missing object: eval_spec"))
            return errors

        dataset_ref = spec.get("dataset_ref")
        if not _is_non_empty_string(dataset_ref):
            errors.append(
                ValidationMessage("TEMPLATE_FIELD_MISSING", "eval_spec.dataset_ref must be a non-empty string")
            )
        elif not _ref_is_valid(dataset_ref):
            errors.append(ValidationMessage("LINK_INVALID_FORMAT", "eval_spec.dataset_ref must be a valid ref"))

        if not _is_non_empty_string(spec.get("protocol")):
            errors.append(ValidationMessage("TEMPLATE_FIELD_MISSING", "eval_spec.protocol must be a non-empty string"))

        metrics = spec.get("metrics")
        if not isinstance(metrics, list) or not metrics:
            errors.append(
                ValidationMessage("TEMPLATE_FIELD_MISSING", "eval_spec.metrics must be a non-empty list")
            )
        else:
            for index, metric in enumerate(metrics, start=1):
                if not isinstance(metric, dict):
                    errors.append(
                        ValidationMessage(
                            "TEMPLATE_FIELD_MISSING",
                            f"eval_spec.metrics[{index}] must be an object",
                        )
                    )
                    continue
                if not _is_non_empty_string(metric.get("name")):
                    errors.append(
                        ValidationMessage(
                            "TEMPLATE_FIELD_MISSING",
                            f"eval_spec.metrics[{index}].name must be a non-empty string",
                        )
                    )
                if not _is_non_empty_string(metric.get("threshold")):
                    errors.append(
                        ValidationMessage(
                            "TEMPLATE_FIELD_MISSING",
                            f"eval_spec.metrics[{index}].threshold must be a non-empty string",
                        )
                    )

        baseline = spec.get("baseline")
        if not isinstance(baseline, dict):
            errors.append(ValidationMessage("TEMPLATE_FIELD_MISSING", "eval_spec.baseline must be an object"))
        else:
            baseline_ref = baseline.get("ref")
            if not _is_non_empty_string(baseline_ref):
                errors.append(
                    ValidationMessage(
                        "TEMPLATE_FIELD_MISSING",
                        "eval_spec.baseline.ref must be a non-empty string",
                    )
                )
            elif not _ref_is_valid(baseline_ref):
                errors.append(ValidationMessage("LINK_INVALID_FORMAT", "eval_spec.baseline.ref must be a valid ref"))
            if not _is_non_empty_string(baseline.get("description")):
                errors.append(
                    ValidationMessage(
                        "TEMPLATE_FIELD_MISSING",
                        "eval_spec.baseline.description must be a non-empty string",
                    )
                )

    return errors


def _load_record(path: Path) -> LoadedRecord:
    match = re.match(r"^(DR-\d{4})", path.stem)
    record = LoadedRecord(path=path, yaml_id=match.group(1) if match else path.stem)

    try:
        text = path.read_text(encoding="utf-8")
        yaml_text, markdown = _extract_front_matter(text)
        doc = yaml.safe_load(yaml_text)
        if not isinstance(doc, dict):
            record.parse_errors.append(ValidationMessage("YAML_PARSE_ERROR", "YAML root must be an object"))
            return record
        record.doc = doc
        if isinstance(doc.get("id"), str):
            record.yaml_id = doc["id"]
        record.heading_counts = _heading_counts(markdown)
        record.headings = _parse_headings(markdown)
        return record
    except yaml.YAMLError:
        record.parse_errors.append(ValidationMessage("YAML_PARSE_ERROR", "Invalid YAML front matter"))
    except ValueError as exc:
        record.parse_errors.append(ValidationMessage("YAML_PARSE_ERROR", str(exc)))
    return record


def _incoming_supersedes(records: list[LoadedRecord]) -> dict[str, int]:
    incoming: dict[str, int] = {}
    for record in records:
        if not isinstance(record.doc, dict):
            continue
        src_id = record.doc.get("id")
        links = record.doc.get("links", []) if isinstance(record.doc.get("links"), list) else []
        for link in links:
            if not isinstance(link, dict) or link.get("rel") != "supersedes":
                continue
            ref = link.get("ref")
            if isinstance(ref, str) and ref.startswith("decision:"):
                target = ref.split("decision:", 1)[1]
                if target == src_id:
                    continue
                incoming[target] = incoming.get(target, 0) + 1
    return incoming


def _record_ids(records: list[LoadedRecord]) -> set[str]:
    ids: set[str] = set()
    for record in records:
        if isinstance(record.doc, dict) and isinstance(record.doc.get("id"), str):
            ids.add(record.doc["id"])
    return ids


def _duplicate_record_ids(records: list[LoadedRecord]) -> set[str]:
    counts: dict[str, int] = {}
    for record in records:
        if isinstance(record.doc, dict) and isinstance(record.doc.get("id"), str):
            decision_id = record.doc["id"]
            counts[decision_id] = counts.get(decision_id, 0) + 1
    return {decision_id for decision_id, count in counts.items() if count > 1}


def _validation_context(records: list[LoadedRecord]) -> ValidationContext:
    return ValidationContext(
        incoming_supersedes=_incoming_supersedes(records),
        all_ids=_record_ids(records),
        duplicate_ids=_duplicate_record_ids(records),
    )


def _validated_links(
    links: list[Any],
    errors: list[ValidationMessage],
    warnings: list[ValidationMessage],
    all_ids: set[str],
) -> list[dict[str, Any]]:
    seen_link_ids: set[str] = set()
    valid_links: list[dict[str, Any]] = []

    for index, link in enumerate(links, start=1):
        if not isinstance(link, dict):
            errors.append(ValidationMessage("YAML_MISSING_KEY", f"links[{index}] must be an object"))
            continue

        for key in ("id", "rel", "artifact_kind", "ref"):
            if key not in link:
                errors.append(ValidationMessage("YAML_MISSING_KEY", f"links[{index}] missing key: {key}"))

        link_id = link.get("id")
        if not _is_non_empty_string(link_id):
            errors.append(ValidationMessage("YAML_MISSING_KEY", f"links[{index}].id must be non-empty"))
        elif link_id in seen_link_ids:
            errors.append(ValidationMessage("LINK_ID_DUPLICATE", f"Duplicate link id in file: {link_id}"))
        else:
            seen_link_ids.add(link_id)

        rel = link.get("rel")
        artifact_kind = link.get("artifact_kind")
        ref = link.get("ref")
        rel_ok = rel in RELS
        kind_ok = artifact_kind in ARTIFACT_KINDS
        ref_ok = _ref_is_valid(ref)

        if not rel_ok:
            errors.append(ValidationMessage("ENUM_INVALID", f"invalid rel in links[{index}]"))
        if not kind_ok:
            errors.append(ValidationMessage("ENUM_INVALID", f"invalid artifact_kind in links[{index}]"))
        if not ref_ok:
            errors.append(ValidationMessage("LINK_INVALID_FORMAT", f"invalid ref in links[{index}]"))

        if isinstance(ref, str) and ref.startswith("decision:"):
            target_id = ref.split("decision:", 1)[1]
            if rel != "supersedes":
                warnings.append(
                    ValidationMessage(
                        "DECISION_REF_NON_SUPERSEDES",
                        f"links[{index}] references a decision with rel={rel}",
                    )
                )
            if target_id not in all_ids:
                warnings.append(
                    ValidationMessage(
                        "DECISION_REF_NOT_FOUND",
                        f"links[{index}] references missing decision: {target_id}",
                    )
                )

        if rel_ok and kind_ok and ref_ok and _is_non_empty_string(link_id):
            valid_links.append(link)

    return valid_links


def _git_commit_warnings(valid_links: list[dict[str, Any]], git_root: Optional[Path]) -> list[ValidationMessage]:
    if git_root is None:
        return []

    warnings: list[ValidationMessage] = []
    checked: set[str] = set()
    for link in valid_links:
        ref = link.get("ref")
        if not isinstance(ref, str) or not ref.startswith("git:commit:"):
            continue
        sha = ref.split("git:commit:", 1)[1]
        if sha in checked:
            continue
        checked.add(sha)
        if not _git_commit_exists(git_root, sha):
            warnings.append(
                ValidationMessage("GIT_COMMIT_NOT_FOUND", f"Referenced commit is not in local Git history: {sha}")
            )
    return warnings


def _validation_messages(
    record: LoadedRecord,
    context: ValidationContext,
    git_root: Optional[Path] = None,
) -> tuple[list[ValidationMessage], list[ValidationMessage], list[dict[str, Any]]]:
    errors = list(record.parse_errors)
    warnings: list[ValidationMessage] = []
    valid_links: list[dict[str, Any]] = []

    doc = record.doc
    if not isinstance(doc, dict):
        return errors, warnings, valid_links

    required_keys = [
        "id",
        "title",
        "status",
        "type",
        "stage",
        "date",
        "owner",
        "stakeholders",
        "template_version",
        "links",
    ]
    for key in required_keys:
        if key not in doc:
            errors.append(ValidationMessage("YAML_MISSING_KEY", f"Missing key: {key}"))

    if "id" in doc and (not isinstance(doc.get("id"), str) or not ID_RE.match(str(doc["id"]))):
        errors.append(ValidationMessage("ID_FORMAT_INVALID", "id must match DR-\\d{4}"))
    elif isinstance(doc.get("id"), str) and doc["id"] in context.duplicate_ids:
        errors.append(ValidationMessage("ID_DUPLICATE", f"Duplicate decision id: {doc['id']}"))
    if "date" in doc and (not isinstance(doc.get("date"), str) or not DATE_RE.match(str(doc["date"]))):
        errors.append(ValidationMessage("ENUM_INVALID", "date must match YYYY-MM-DD"))
    if "status" in doc and doc.get("status") not in STATUSES:
        errors.append(ValidationMessage("ENUM_INVALID", "invalid status"))
    if "type" in doc and doc.get("type") not in TYPES:
        errors.append(ValidationMessage("ENUM_INVALID", "invalid type"))
    if "stage" in doc and doc.get("stage") not in STAGES:
        errors.append(ValidationMessage("ENUM_INVALID", "invalid stage"))
    if "template_version" in doc and doc.get("template_version") != "1.0":
        errors.append(ValidationMessage("ENUM_INVALID", "template_version must be 1.0"))

    if "owner" in doc and not _is_non_empty_string(doc.get("owner")):
        errors.append(ValidationMessage("YAML_MISSING_KEY", "owner must be a non-empty string"))
    if "title" in doc and not _is_non_empty_string(doc.get("title")):
        errors.append(ValidationMessage("YAML_MISSING_KEY", "title must be a non-empty string"))
    if "stakeholders" in doc and not isinstance(doc.get("stakeholders"), list):
        errors.append(ValidationMessage("YAML_MISSING_KEY", "stakeholders must be a list"))
    if "links" in doc and not isinstance(doc.get("links"), list):
        errors.append(ValidationMessage("YAML_MISSING_KEY", "links must be a list"))

    warnings.extend(_stakeholder_duplicate_warnings(doc.get("stakeholders")))

    for heading in REQUIRED_HEADINGS:
        count = record.heading_counts.get(heading, 0)
        if count == 0:
            errors.append(ValidationMessage("HEADING_MISSING", f"Missing heading: ## {heading}"))
        elif count > 1:
            errors.append(ValidationMessage("HEADING_DUPLICATE", f"Heading appears multiple times: ## {heading}"))

    if all(record.heading_counts.get(heading, 0) == 1 for heading in REQUIRED_HEADINGS):
        for heading in CORE_HEADINGS:
            if not _is_non_empty_section(record.headings.get(heading)):
                errors.append(ValidationMessage("SECTION_EMPTY", f"Section is empty: ## {heading}"))
        alternatives = record.headings.get("Alternatives", "")
        if not alternatives.strip():
            errors.append(ValidationMessage("SECTION_EMPTY", "Section is empty: ## Alternatives"))

    errors.extend(_template_validation_errors(doc))

    links = doc.get("links", []) if isinstance(doc.get("links"), list) else []
    valid_links = _validated_links(links, errors, warnings, context.all_ids)
    warnings.extend(_git_commit_warnings(valid_links, git_root))

    status = doc.get("status")
    decision_type = doc.get("type")
    if status != "proposed":
        if decision_type == "generic" and len(valid_links) < 1:
            errors.append(ValidationMessage("MIN_LINKS_NOT_MET", "generic requires at least one valid link"))
        elif decision_type == "model":
            has_impl_code = any(
                link.get("rel") == "implements" and link.get("artifact_kind") == "code" for link in valid_links
            )
            has_support = any(
                link.get("rel") == "supported_by" and link.get("artifact_kind") in {"document", "issue"}
                for link in valid_links
            )
            if not (has_impl_code and has_support):
                errors.append(
                    ValidationMessage(
                        "MIN_LINKS_NOT_MET",
                        "model requires implements->code and supported_by->(document|issue)",
                    )
                )
        elif decision_type == "evaluation_protocol":
            has_eval = any(
                link.get("rel") == "evaluated_by" and link.get("artifact_kind") in {"experiment_run", "document"}
                for link in valid_links
            )
            has_dataset = any(
                link.get("artifact_kind") == "data" and link.get("rel") in {"supported_by", "evaluated_by"}
                for link in valid_links
            )
            if not (has_eval and has_dataset):
                errors.append(
                    ValidationMessage(
                        "MIN_LINKS_NOT_MET",
                        "evaluation_protocol requires evaluated_by and data link via supported_by|evaluated_by",
                    )
                )

    if status == "superseded":
        decision_id = doc.get("id")
        if isinstance(decision_id, str) and context.incoming_supersedes.get(decision_id, 0) < 1:
            errors.append(
                ValidationMessage(
                    "SUPERSEDED_INCONSISTENT",
                    "status superseded requires incoming supersedes edge from another decision",
                )
            )

    return errors, warnings, valid_links


def _yaml_valid(doc: dict[str, Any]) -> bool:
    required = (
        isinstance(doc.get("id"), str)
        and bool(ID_RE.match(doc["id"]))
        and _is_non_empty_string(doc.get("title"))
        and doc.get("status") in STATUSES
        and doc.get("type") in TYPES
        and doc.get("stage") in STAGES
        and isinstance(doc.get("date"), str)
        and bool(DATE_RE.match(doc["date"]))
        and _is_non_empty_string(doc.get("owner"))
        and doc.get("template_version") == "1.0"
        and isinstance(doc.get("stakeholders"), list)
        and isinstance(doc.get("links"), list)
    )
    if not required:
        return False
    return not any(message.code == "TEMPLATE_FIELD_MISSING" for message in _template_validation_errors(doc))


def _build_decision(path: Path) -> DecisionComputed:
    text = path.read_text(encoding="utf-8")
    yaml_text, markdown = _extract_front_matter(text)
    doc = yaml.safe_load(yaml_text)
    if not isinstance(doc, dict):
        raise ValueError("YAML root must be object")

    headings = _parse_headings(markdown)
    links = doc.get("links") if isinstance(doc.get("links"), list) else []
    links_sorted = sorted(
        (link for link in links if isinstance(link, dict)),
        key=lambda link: (
            str(link.get("rel", "")),
            str(link.get("artifact_kind", "")),
            str(link.get("ref", "")),
            str(link.get("label", "")),
        ),
    )

    stakeholders = _stable_stakeholders(doc.get("stakeholders", []))
    valid_yaml = _yaml_valid(doc)

    has_map = {name: 1 if name in headings else 0 for name in REQUIRED_HEADINGS}
    alternatives_is_na = 1 if headings.get("Alternatives", "").strip().lower() in {"n/a", "na"} else 0
    non_empty_core = 0
    for heading in CORE_HEADINGS:
        if _is_non_empty_section(headings.get(heading)):
            non_empty_core += 1

    structure_score = 1 if all(has_map[heading] == 1 for heading in REQUIRED_HEADINGS) else 0
    content_score = non_empty_core / 4
    yaml_score = 1 if valid_yaml else 0
    score_completeness = _round3(0.2 * structure_score + 0.6 * content_score + 0.2 * yaml_score)

    rel_counts = {rel: 0 for rel in RELS}
    valid_links: list[dict[str, Any]] = []
    unique_artifact_refs_by_kind: dict[str, set[str]] = {kind: set() for kind in ARTIFACT_KINDS}
    decision_targets: set[str] = set()
    rel_used: set[str] = set()

    for link in links_sorted:
        rel = link.get("rel")
        artifact_kind = link.get("artifact_kind")
        ref = link.get("ref")
        if rel in RELS:
            rel_counts[rel] += 1
        if rel in RELS and artifact_kind in ARTIFACT_KINDS and _ref_is_valid(ref):
            valid_links.append(link)
            rel_used.add(rel)
            if isinstance(ref, str) and ref.startswith("decision:"):
                decision_targets.add(ref)
            elif isinstance(ref, str):
                unique_artifact_refs_by_kind[artifact_kind].add(ref)

    unique_artifacts_total = sum(len(values) for values in unique_artifact_refs_by_kind.values())
    unique_artifacts_by_kind = {kind: len(values) for kind, values in unique_artifact_refs_by_kind.items()}
    unique_decision_targets_total = len(decision_targets)

    score_connectedness = _round3(
        min(1.0, ((unique_artifacts_total / 4) * 0.6) + ((len(rel_used) / 4) * 0.4))
    )
    score_inclusiveness = _round3(min(1.0, len(stakeholders) / 3))

    status = doc.get("status")
    decision_type = doc.get("type")
    has_minimum_trace_links = 0
    if status == "proposed":
        has_minimum_trace_links = 1
    elif decision_type == "generic":
        has_minimum_trace_links = 1 if len(valid_links) >= 1 else 0
    elif decision_type == "model":
        has_impl_code = any(
            link.get("rel") == "implements" and link.get("artifact_kind") == "code" for link in valid_links
        )
        has_support = any(
            link.get("rel") == "supported_by" and link.get("artifact_kind") in {"document", "issue"}
            for link in valid_links
        )
        has_minimum_trace_links = 1 if has_impl_code and has_support else 0
    elif decision_type == "evaluation_protocol":
        has_eval = any(
            link.get("rel") == "evaluated_by" and link.get("artifact_kind") in {"experiment_run", "document"}
            for link in valid_links
        )
        has_dataset = any(
            link.get("artifact_kind") == "data" and link.get("rel") in {"supported_by", "evaluated_by"}
            for link in valid_links
        )
        has_minimum_trace_links = 1 if has_eval and has_dataset else 0

    traceability_minimum = {"generic": 1, "model": 2, "evaluation_protocol": 2}.get(decision_type, 1)
    if has_minimum_trace_links == 0:
        score_traceability = 0.0
    else:
        score_traceability = _round3(min(1.0, len(valid_links) / (traceability_minimum + 2)))

    return DecisionComputed(
        raw=doc,
        links_sorted=links_sorted,
        headings=headings,
        stakeholders=stakeholders,
        has_minimum_trace_links=has_minimum_trace_links,
        score_completeness=score_completeness,
        score_connectedness=score_connectedness,
        score_inclusiveness=score_inclusiveness,
        score_traceability=score_traceability,
        rel_counts=rel_counts,
        unique_artifacts_by_kind=unique_artifacts_by_kind,
        unique_artifacts_total=unique_artifacts_total,
        unique_decision_targets_total=unique_decision_targets_total,
        alternatives_is_na=alternatives_is_na,
    )


@app.command()
def report(root: Optional[Path] = typer.Option(None, "--root", help="Repository root containing decisions/.")) -> None:
    """Generate exports and metrics."""
    root = _resolve_root(root)
    decisions_dir = root / "decisions"
    if not decisions_dir.exists():
        raise typer.Exit(code=2)

    files = sorted(decisions_dir.glob("*.md"), key=lambda path: path.name)
    loaded_records = [_load_record(path) for path in files]
    context = _validation_context(loaded_records)
    git_root = _git_repo_root(root)

    has_validation_failures = False
    for record in loaded_records:
        errors, warnings, _ = _validation_messages(record, context, git_root)
        record_id = record.yaml_id or "UNKNOWN"
        for error in errors:
            has_validation_failures = True
            typer.echo(f"FAIL {record_id}: {error.code}: {error.message}")
        for warning in warnings:
            typer.echo(f"WARN {record_id}: {warning.code}: {warning.message}")
    if has_validation_failures:
        raise typer.Exit(code=3)

    decisions: list[DecisionComputed] = []
    for path in files:
        decision = _build_decision(path)
        decisions.append(decision)

    decisions.sort(key=lambda decision: str(decision.raw.get("id", "")))

    index_payload: list[dict[str, Any]] = []
    artifact_nodes: dict[str, dict[str, Any]] = {}
    decision_nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    csv_rows: list[dict[str, Any]] = []
    stage_counts: dict[str, int] = {}
    type_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}

    smell_alternatives_na = 0
    smell_weak_trace = 0
    smell_no_evidence = 0

    for decision in decisions:
        doc = decision.raw
        decision_id = str(doc["id"])
        decision_node_id = f"decision:{decision_id}"
        decision_nodes.append({"id": decision_node_id, "kind": "decision", "label": str(doc["title"])})

        stage = str(doc["stage"])
        decision_type = str(doc["type"])
        status = str(doc["status"])
        stage_counts[stage] = stage_counts.get(stage, 0) + 1
        type_counts[decision_type] = type_counts.get(decision_type, 0) + 1
        status_counts[status] = status_counts.get(status, 0) + 1

        has_context = 1 if _is_non_empty_section(decision.headings.get("Context")) else 0
        has_decision = 1 if _is_non_empty_section(decision.headings.get("Decision")) else 0
        has_rationale = 1 if _is_non_empty_section(decision.headings.get("Rationale")) else 0
        has_alt_heading = 1 if "Alternatives" in decision.headings else 0
        has_consequences = 1 if _is_non_empty_section(decision.headings.get("Consequences")) else 0
        has_owner = 1 if _is_non_empty_string(doc.get("owner")) else 0
        has_stakeholders = 1 if len(decision.stakeholders) > 0 else 0

        if decision.alternatives_is_na == 1:
            smell_alternatives_na += 1
        if decision.score_traceability < 0.5:
            smell_weak_trace += 1
        if decision.rel_counts["supported_by"] == 0:
            smell_no_evidence += 1

        for link in decision.links_sorted:
            ref = link.get("ref")
            if not isinstance(ref, str):
                continue
            target_id = _infer_target_id(ref)
            label = str(link.get("label") or ref)
            if not ref.startswith("decision:"):
                existing = artifact_nodes.get(target_id)
                candidate = {
                    "id": target_id,
                    "artifact_kind": str(link.get("artifact_kind", "")),
                    "ref": ref,
                    "label": label,
                }
                if existing is None:
                    artifact_nodes[target_id] = candidate
                elif label < str(existing.get("label", "")):
                    existing["label"] = label
            edges.append(
                {
                    "source": decision_node_id,
                    "target": target_id,
                    "rel": str(link.get("rel", "")),
                    "artifact_kind": str(link.get("artifact_kind", "")),
                    "label": label,
                }
            )

        index_payload.append(
            {
                "id": decision_id,
                "title": str(doc["title"]),
                "status": status,
                "type": decision_type,
                "stage": stage,
                "date": str(doc["date"]),
                "owner": str(doc["owner"]),
                "stakeholders": decision.stakeholders,
                "link_count": len(decision.links_sorted),
                "links": [
                    {
                        "artifact_kind": str(link.get("artifact_kind", "")),
                        "label": str(link.get("label") or link.get("ref", "")),
                        "ref": str(link.get("ref", "")),
                        "rel": str(link.get("rel", "")),
                        "target": _infer_target_id(str(link.get("ref", ""))),
                    }
                    for link in decision.links_sorted
                    if isinstance(link.get("ref"), str)
                ],
                "sections": {heading: decision.headings.get(heading, "") for heading in REQUIRED_HEADINGS},
                "scores": {
                    "completeness": decision.score_completeness,
                    "connectedness": decision.score_connectedness,
                    "inclusiveness": decision.score_inclusiveness,
                    "traceability": decision.score_traceability,
                },
            }
        )

        csv_rows.append(
            {
                "decision_id": decision_id,
                "title": str(doc["title"]),
                "status": status,
                "type": decision_type,
                "stage": stage,
                "date": str(doc["date"]),
                "owner": str(doc["owner"]),
                "link_total": len(decision.links_sorted),
                "links_by_rel_implements": decision.rel_counts["implements"],
                "links_by_rel_evaluated_by": decision.rel_counts["evaluated_by"],
                "links_by_rel_supported_by": decision.rel_counts["supported_by"],
                "links_by_rel_supersedes": decision.rel_counts["supersedes"],
                "unique_artifacts_total": decision.unique_artifacts_total,
                "unique_artifacts_by_kind_code": decision.unique_artifacts_by_kind["code"],
                "unique_artifacts_by_kind_data": decision.unique_artifacts_by_kind["data"],
                "unique_artifacts_by_kind_experiment_run": decision.unique_artifacts_by_kind["experiment_run"],
                "unique_artifacts_by_kind_document": decision.unique_artifacts_by_kind["document"],
                "unique_artifacts_by_kind_issue": decision.unique_artifacts_by_kind["issue"],
                "unique_decision_targets_total": decision.unique_decision_targets_total,
                "has_context": has_context,
                "has_decision": has_decision,
                "has_rationale": has_rationale,
                "has_alternatives_heading": has_alt_heading,
                "has_consequences": has_consequences,
                "alternatives_is_na": decision.alternatives_is_na,
                "has_minimum_trace_links": decision.has_minimum_trace_links,
                "has_owner": has_owner,
                "has_stakeholders": has_stakeholders,
                "score_completeness": decision.score_completeness,
                "score_connectedness": decision.score_connectedness,
                "score_inclusiveness": decision.score_inclusiveness,
                "score_traceability": decision.score_traceability,
            }
        )

    artifact_list = sorted(artifact_nodes.values(), key=lambda artifact: str(artifact["id"]))
    nodes = [{"id": artifact["id"], "kind": "artifact", "label": artifact["label"]} for artifact in artifact_list]
    nodes.extend(decision_nodes)
    nodes.sort(key=lambda node: (str(node["kind"]), str(node["id"])))
    edges.sort(key=lambda edge: (str(edge["source"]), str(edge["rel"]), str(edge["target"])))

    _json_dump(root / "decisions" / "index.json", index_payload)
    _json_dump(root / "decisions" / "graph.json", {"nodes": nodes, "edges": edges})
    _json_dump(root / "decisions" / "artifacts.json", artifact_list)

    csv_headers = [
        "decision_id",
        "title",
        "status",
        "type",
        "stage",
        "date",
        "owner",
        "link_total",
        "links_by_rel_implements",
        "links_by_rel_evaluated_by",
        "links_by_rel_supported_by",
        "links_by_rel_supersedes",
        "unique_artifacts_total",
        "unique_artifacts_by_kind_code",
        "unique_artifacts_by_kind_data",
        "unique_artifacts_by_kind_experiment_run",
        "unique_artifacts_by_kind_document",
        "unique_artifacts_by_kind_issue",
        "unique_decision_targets_total",
        "has_context",
        "has_decision",
        "has_rationale",
        "has_alternatives_heading",
        "has_consequences",
        "alternatives_is_na",
        "has_minimum_trace_links",
        "has_owner",
        "has_stakeholders",
        "score_completeness",
        "score_connectedness",
        "score_inclusiveness",
        "score_traceability",
    ]

    metrics_path = root / "reports" / "metrics.csv"
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    with metrics_path.open("w", encoding="utf-8", newline="") as file_pointer:
        writer = csv.DictWriter(file_pointer, fieldnames=csv_headers, lineterminator="\r\n")
        writer.writeheader()
        for row in csv_rows:
            writer.writerow(row)

    total = len(decisions)
    avg_completeness = _round3(sum(item.score_completeness for item in decisions) / total) if total else 0.0
    avg_connectedness = _round3(sum(item.score_connectedness for item in decisions) / total) if total else 0.0
    avg_inclusiveness = _round3(sum(item.score_inclusiveness for item in decisions) / total) if total else 0.0
    avg_traceability = _round3(sum(item.score_traceability for item in decisions) / total) if total else 0.0

    report_lines = [
        "# Decision Tracker Report",
        "## Counts",
        f"- total decisions: {total}",
        "- by stage:",
    ]
    for key in sorted(stage_counts):
        report_lines.append(f"  - {key}: {stage_counts[key]}")
    report_lines.append("- by type:")
    for key in sorted(type_counts):
        report_lines.append(f"  - {key}: {type_counts[key]}")
    report_lines.append("- by status:")
    for key in sorted(status_counts):
        report_lines.append(f"  - {key}: {status_counts[key]}")
    report_lines.extend(
        [
            "",
            "## Average scores",
            f"- completeness: {avg_completeness}",
            f"- connectedness: {avg_connectedness}",
            f"- inclusiveness: {avg_inclusiveness}",
            f"- traceability: {avg_traceability}",
            "",
            "## Smells",
            f"- S2 Alternatives N/A: {smell_alternatives_na}",
            f"- S3 Weak traceability: {smell_weak_trace}",
            f"- S4 No evidence link: {smell_no_evidence}",
        ]
    )

    report_path = root / "reports" / "report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    typer.echo(
        "Generated decisions/index.json, decisions/graph.json, decisions/artifacts.json, reports/metrics.csv, reports/report.md"
    )


@app.command()
def validate(
    all: bool = typer.Option(False, "--all"),
    id: str = typer.Option(None, "--id"),
    root: Optional[Path] = typer.Option(None, "--root", help="Repository root containing decisions/."),
) -> None:
    """Validate one record or all records."""
    root = _resolve_root(root)
    decisions_dir = root / "decisions"
    if not decisions_dir.exists():
        raise typer.Exit(code=2)

    records = [_load_record(path) for path in sorted(decisions_dir.glob("DR-*.md"), key=lambda path: path.name)]
    context = _validation_context(records)
    git_root = _git_repo_root(root)

    if all or not id:
        selected = records
    else:
        selected = [record for record in records if record.yaml_id == id]
        if not selected:
            typer.echo(f"FAIL {id}: YAML_MISSING_KEY: Decision id not found")
            raise typer.Exit(code=3)

    has_failures = False
    for record in selected:
        errors, warnings, _ = _validation_messages(record, context, git_root)
        record_id = record.yaml_id or "UNKNOWN"
        if errors:
            has_failures = True
            for error in errors:
                typer.echo(f"FAIL {record_id}: {error.code}: {error.message}")
        for warning in warnings:
            typer.echo(f"WARN {record_id}: {warning.code}: {warning.message}")
        if not errors:
            typer.echo(f"OK {record_id}")

    raise typer.Exit(code=3 if has_failures else 0)


@app.command()
def new(
    title: str = typer.Option(..., "--title"),
    stage: str = typer.Option(..., "--stage"),
    type: str = typer.Option(..., "--type"),
    owner: str = typer.Option(..., "--owner"),
    stakeholders: str = typer.Option("", "--stakeholders"),
    git_head: bool = typer.Option(False, "--git-head", help="Add the current Git HEAD commit as a code link."),
    root: Optional[Path] = typer.Option(None, "--root", help="Repository root containing decisions/."),
) -> None:
    """Create a new Decision Record."""
    if stage not in STAGES:
        raise typer.BadParameter("stage must be one of data|training|evaluation|deployment|monitoring")
    if type not in TYPES:
        raise typer.BadParameter("type must be one of model|evaluation_protocol|generic")

    root = _resolve_root(root)
    decisions_dir = root / "decisions"
    try:
        decisions_dir.mkdir(parents=True, exist_ok=True)
        next_id = _next_decision_id(decisions_dir)
        slug = _slugify_title(title)
        out_path = decisions_dir / f"{next_id}-{slug}.md"

        payload: dict[str, Any] = {
            "id": next_id,
            "title": title,
            "status": "proposed",
            "type": type,
            "stage": stage,
            "date": str(date.today()),
            "owner": owner,
            "stakeholders": _parse_stakeholders_csv(stakeholders),
            "template_version": "1.0",
            "links": [],
        }
        if git_head:
            try:
                head_sha = _resolve_git_head(root)
            except RuntimeError as exc:
                typer.echo(f"FAIL GIT_HEAD_UNAVAILABLE: {exc}")
                raise typer.Exit(code=2)
            payload["links"].append(
                {
                    "id": "L-0001",
                    "rel": "implements",
                    "artifact_kind": "code",
                    "ref": f"git:commit:{head_sha}",
                    "label": "Current HEAD commit",
                    "note": "",
                }
            )
        payload.update(_template_payload(type))

        yaml_text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=False).strip()
        body = "\n".join(
            [
                "---",
                yaml_text,
                "---",
                "",
                "## Context",
                "TODO",
                "",
                "## Decision",
                "TODO",
                "",
                "## Rationale",
                "TODO",
                "",
                "## Alternatives",
                "N/A",
                "",
                "## Consequences",
                "TODO",
                "",
            ]
        )
        out_path.write_text(body, encoding="utf-8")
    except OSError:
        raise typer.Exit(code=2)

    relative_path = out_path.relative_to(root).as_posix()
    typer.echo(f"Created {relative_path}")


if __name__ == "__main__":
    app()
