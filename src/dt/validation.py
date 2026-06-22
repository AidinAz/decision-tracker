from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any, Optional

import yaml

from dt.constants import (
    ARTIFACT_KINDS,
    CORE_HEADINGS,
    DATE_RE,
    ID_RE,
    RECONSTRUCTION_CONFIDENCE,
    RELS,
    REQUIRED_HEADINGS,
    STAGES,
    STATUSES,
    TYPES,
)
from dt.git import _git_commit_check
from dt.markdown import _extract_front_matter, _heading_counts, _parse_headings
from dt.models import LoadedRecord, ValidationContext, ValidationMessage
from dt.refs import _ref_is_valid
from dt.templates import _template_validation_errors
from dt.utils import _is_non_empty_section, _is_non_empty_string


def _validate_date_value(value: Any) -> Optional[ValidationMessage]:
    if not isinstance(value, str):
        return ValidationMessage(
            "ENUM_INVALID",
            'date must be a quoted string in YYYY-MM-DD form, for example date: "2026-03-14"',
        )
    if not DATE_RE.match(value):
        return ValidationMessage("ENUM_INVALID", "date must match YYYY-MM-DD")
    try:
        date.fromisoformat(value)
    except ValueError:
        return ValidationMessage("ENUM_INVALID", "date must be a real calendar date in YYYY-MM-DD form")
    return None


def _validate_template_version_value(value: Any) -> Optional[ValidationMessage]:
    if not isinstance(value, str):
        return ValidationMessage("ENUM_INVALID", 'template_version must be the quoted string "1.0"')
    if value != "1.0":
        return ValidationMessage("ENUM_INVALID", "template_version must be 1.0")
    return None


def _validate_original_decision_date(value: Any) -> bool:
    if value == "unknown":
        return True
    return _validate_date_value(value) is None


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


def _todo_section_warnings(headings: dict[str, str]) -> list[ValidationMessage]:
    warnings: list[ValidationMessage] = []
    for heading in REQUIRED_HEADINGS:
        body = headings.get(heading, "").strip()
        if re.match(r"^TODO\b", body, flags=re.IGNORECASE):
            warnings.append(ValidationMessage("TODO_SECTION", f"Section still contains TODO placeholder: ## {heading}"))
    return warnings


def _reconstruction_validation_errors(doc: dict[str, Any]) -> list[ValidationMessage]:
    if "reconstruction" not in doc:
        return []
    errors: list[ValidationMessage] = []
    reconstruction = doc.get("reconstruction")
    if not isinstance(reconstruction, dict):
        return [ValidationMessage("RECONSTRUCTION_INVALID", "reconstruction must be an object when present")]

    if reconstruction.get("mode") != "backfill":
        errors.append(ValidationMessage("RECONSTRUCTION_INVALID", "reconstruction.mode must be backfill"))

    original_decision_date = reconstruction.get("original_decision_date")
    if not _validate_original_decision_date(original_decision_date):
        errors.append(
            ValidationMessage(
                "RECONSTRUCTION_INVALID",
                'reconstruction.original_decision_date must be "unknown" or YYYY-MM-DD',
            )
        )

    confidence = reconstruction.get("evidence_confidence")
    if confidence not in RECONSTRUCTION_CONFIDENCE:
        errors.append(
            ValidationMessage(
                "RECONSTRUCTION_INVALID",
                "reconstruction.evidence_confidence must be one of low|medium|high",
            )
        )

    evidence_sources = reconstruction.get("evidence_sources")
    if not isinstance(evidence_sources, list) or not evidence_sources:
        errors.append(
            ValidationMessage(
                "RECONSTRUCTION_INVALID",
                "reconstruction.evidence_sources must be a non-empty list",
            )
        )
    else:
        for index, ref in enumerate(evidence_sources, start=1):
            if not isinstance(ref, str) or not _ref_is_valid(ref):
                errors.append(
                    ValidationMessage(
                        "RECONSTRUCTION_INVALID",
                        f"reconstruction.evidence_sources[{index}] must be a valid ref",
                    )
                )

    known_gaps = reconstruction.get("known_gaps")
    if known_gaps is None:
        errors.append(ValidationMessage("RECONSTRUCTION_INVALID", "reconstruction.known_gaps must be a list"))
    elif not isinstance(known_gaps, list) or any(not isinstance(item, str) for item in known_gaps):
        errors.append(ValidationMessage("RECONSTRUCTION_INVALID", "reconstruction.known_gaps must be a list of strings"))

    return errors


def _review_validation_errors(doc: dict[str, Any]) -> list[ValidationMessage]:
    if "review" not in doc:
        return []
    review = doc.get("review")
    if not isinstance(review, dict):
        return [ValidationMessage("REVIEW_INVALID", "review must be an object when present")]

    errors: list[ValidationMessage] = []
    if review.get("status") not in {"pending", "reviewed", "changes_requested"}:
        errors.append(
            ValidationMessage("REVIEW_INVALID", "review.status must be one of pending|reviewed|changes_requested")
        )
    reviewed_by = review.get("reviewed_by")
    if not isinstance(reviewed_by, list) or any(not isinstance(item, str) for item in reviewed_by):
        errors.append(ValidationMessage("REVIEW_INVALID", "review.reviewed_by must be a list of strings"))
    reviewed_date = review.get("reviewed_date")
    if not _validate_original_decision_date(reviewed_date):
        errors.append(ValidationMessage("REVIEW_INVALID", 'review.reviewed_date must be "unknown" or YYYY-MM-DD'))
    if "notes" in review and not isinstance(review.get("notes"), str):
        errors.append(ValidationMessage("REVIEW_INVALID", "review.notes must be a string"))
    return errors


def _review_validation_warnings(doc: dict[str, Any]) -> list[ValidationMessage]:
    if "review" not in doc:
        return []
    review = doc.get("review")
    if not isinstance(review, dict):
        return []

    status = review.get("status")
    if status not in {"pending", "reviewed", "changes_requested"}:
        return []

    warnings: list[ValidationMessage] = []
    reviewed_by = review.get("reviewed_by")
    if status != "pending" and isinstance(reviewed_by, list):
        reviewers = [item.strip() for item in reviewed_by if isinstance(item, str) and item.strip()]
        if not reviewers:
            warnings.append(
                ValidationMessage(
                    "REVIEW_INCOMPLETE",
                    f"review.status {status} should include at least one reviewer",
                )
            )

    reviewed_date = review.get("reviewed_date")
    if status != "pending" and reviewed_date == "unknown":
        warnings.append(
            ValidationMessage(
                "REVIEW_INCOMPLETE",
                f"review.status {status} should include a reviewed_date",
            )
        )

    notes = review.get("notes", "")
    if status == "changes_requested" and isinstance(notes, str) and not notes.strip():
        warnings.append(
            ValidationMessage(
                "REVIEW_INCOMPLETE",
                "review.status changes_requested should include notes",
            )
        )
    return warnings


def _backfill_checklist_warnings(doc: dict[str, Any], headings: dict[str, str]) -> list[ValidationMessage]:
    reconstruction = doc.get("reconstruction")
    if not isinstance(reconstruction, dict) or reconstruction.get("mode") != "backfill":
        return []
    body = headings.get("Backfill Review Checklist", "")
    if "- [ ]" in body:
        return [
            ValidationMessage(
                "BACKFILL_CHECKLIST_INCOMPLETE",
                "Backfill review checklist has unchecked items",
            )
        ]
    return []


def _path_ref_warnings(valid_links: list[dict[str, Any]], root: Optional[Path]) -> list[ValidationMessage]:
    if root is None:
        return []
    warnings: list[ValidationMessage] = []
    for index, link in enumerate(valid_links, start=1):
        ref = link.get("ref")
        if not isinstance(ref, str) or not ref.startswith("path:"):
            continue
        relative = ref.split("path:", 1)[1]
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts:
            warnings.append(
                ValidationMessage(
                    "PATH_REF_NOT_PORTABLE",
                    f"links[{index}] uses an absolute or parent-relative path; use a project-local relative path for traceability across machines: {ref}",
                )
            )
            continue
        if not (root / path).exists():
            warnings.append(
                ValidationMessage("PATH_REF_NOT_FOUND", f"links[{index}] references missing local path: {ref}")
            )
    return warnings


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
        check = _git_commit_check(git_root, sha)
        if check.status == "missing":
            warnings.append(
                ValidationMessage("GIT_COMMIT_NOT_FOUND", f"Referenced commit is not in local Git history: {sha}")
            )
        elif check.status == "unavailable":
            detail = f" ({check.detail})" if check.detail else ""
            warnings.append(
                ValidationMessage(
                    "GIT_COMMIT_CHECK_UNAVAILABLE",
                    f"Could not check referenced Git commit{detail}: {sha}",
                )
            )
    return warnings


def _validation_messages(
    record: LoadedRecord,
    context: ValidationContext,
    git_root: Optional[Path] = None,
    root: Optional[Path] = None,
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
    if "date" in doc:
        date_error = _validate_date_value(doc.get("date"))
        if date_error is not None:
            errors.append(date_error)
    if "status" in doc and doc.get("status") not in STATUSES:
        errors.append(ValidationMessage("ENUM_INVALID", "invalid status"))
    if "type" in doc and doc.get("type") not in TYPES:
        errors.append(ValidationMessage("ENUM_INVALID", "invalid type"))
    if "stage" in doc and doc.get("stage") not in STAGES:
        errors.append(ValidationMessage("ENUM_INVALID", "invalid stage"))
    if "template_version" in doc:
        template_version_error = _validate_template_version_value(doc.get("template_version"))
        if template_version_error is not None:
            errors.append(template_version_error)

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
        warnings.extend(_todo_section_warnings(record.headings))

    errors.extend(_template_validation_errors(doc))
    errors.extend(_reconstruction_validation_errors(doc))
    errors.extend(_review_validation_errors(doc))
    warnings.extend(_review_validation_warnings(doc))
    warnings.extend(_backfill_checklist_warnings(doc, record.headings))

    links = doc.get("links", []) if isinstance(doc.get("links"), list) else []
    valid_links = _validated_links(links, errors, warnings, context.all_ids)
    warnings.extend(_git_commit_warnings(valid_links, git_root))
    warnings.extend(_path_ref_warnings(valid_links, root))

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
    return not any(
        message.code in {"TEMPLATE_FIELD_MISSING", "RECONSTRUCTION_INVALID", "REVIEW_INVALID"}
        for message in [*_template_validation_errors(doc), *_reconstruction_validation_errors(doc), *_review_validation_errors(doc)]
    )
