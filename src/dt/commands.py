from __future__ import annotations

import json
import shutil
import subprocess
from datetime import date
from pathlib import Path
from typing import Optional

import typer

from dt import __version__
from dt.constants import DISCOVER_KEYWORDS, RECONSTRUCTION_CONFIDENCE, STAGES, TYPES
from dt.git import GitLogError, _git_log_candidates, _git_repo_root, _resolve_git_head
from dt.markdown import _write_decision_file
from dt.models import DoctorCheck
from dt.paths import _next_decision_id, _resolve_root
from dt.refs import _evidence_link_for_ref, _validate_evidence_refs
from dt.reporting import generate_report
from dt.scaffold import GITIGNORE_END, GITIGNORE_START, initialize_project
from dt.site import build_site as build_static_site
from dt.templates import _template_payload
from dt.utils import _parse_list_text, _parse_stakeholders_csv, _record_file_suffix
from dt.validation import _load_record, _validate_original_decision_date, _validation_context, _validation_messages


def _prompt_if_missing(value: Optional[str], label: str, default: Optional[str] = None) -> str:
    if value is not None:
        return value
    if default is None:
        return typer.prompt(label)
    return typer.prompt(label, default=default)


def init_command(root: Optional[Path], force: bool) -> None:
    initialize_project(_resolve_root(root), force)


def build_site_command_handler(root: Optional[Path], site_dir: Optional[Path], force: bool) -> None:
    resolved_root = _resolve_root(root)
    resolved_site_dir = site_dir.absolute() if site_dir else resolved_root / "_site"
    build_static_site(resolved_root, resolved_site_dir, force=force)


def report_command(root: Optional[Path]) -> None:
    generate_report(_resolve_root(root))


def discover_command(root: Optional[Path], since: Optional[str], limit: int, keywords: str) -> None:
    if limit < 1:
        raise typer.BadParameter("limit must be at least 1")

    resolved_root = _resolve_root(root)
    keyword_values = _parse_list_text(keywords)
    if not keyword_values:
        raise typer.BadParameter("keywords must include at least one value")
    if since is not None:
        try:
            date.fromisoformat(since)
        except ValueError:
            typer.echo(f"FAIL DISCOVER_GIT_FAILED: invalid --since value: {since}. Use YYYY-MM-DD.")
            raise typer.Exit(code=2)

    try:
        candidates = _git_log_candidates(resolved_root, keyword_values, since, limit)
    except GitLogError as exc:
        typer.echo(f"FAIL DISCOVER_GIT_FAILED: {exc}")
        raise typer.Exit(code=2)
    if not candidates:
        typer.echo("No candidate decision evidence found.")
        return

    typer.echo(f"Found {len(candidates)} candidate decision evidence item(s).")
    for index, candidate in enumerate(candidates, start=1):
        typer.echo("")
        typer.echo(f"[{index}] {candidate.title}")
        typer.echo(f"    evidence: git:commit:{candidate.sha}")
        typer.echo(f"    suggested stage: {candidate.stage}")
        typer.echo(f"    suggested type: {candidate.decision_type}")


def backfill_command(
    title: Optional[str],
    stage: Optional[str],
    decision_type: Optional[str],
    owner: Optional[str],
    stakeholders: str,
    original_decision_date: Optional[str],
    evidence_refs: Optional[str],
    confidence: Optional[str],
    known_gaps: str,
    context: Optional[str],
    decision: Optional[str],
    rationale: Optional[str],
    alternatives: Optional[str],
    consequences: Optional[str],
    root: Optional[Path],
) -> None:
    resolved_root = _resolve_root(root)
    decisions_dir = resolved_root / "decisions"
    if not decisions_dir.is_dir():
        typer.echo(f"FAIL DECISIONS_DIR_MISSING: No decisions/ directory found at {resolved_root}. Run `dt init` first.")
        raise typer.Exit(code=2)

    title_value = _prompt_if_missing(title, "Decision title")
    stage_value = _prompt_if_missing(stage, "Stage", "training")
    type_value = _prompt_if_missing(decision_type, "Type", "generic")
    owner_value = _prompt_if_missing(owner, "Owner")
    original_date_value = _prompt_if_missing(original_decision_date, "Original decision date", "unknown")
    evidence_text = _prompt_if_missing(evidence_refs, "Evidence refs")
    confidence_value = _prompt_if_missing(confidence, "Evidence confidence", "medium")

    if stage_value not in STAGES:
        raise typer.BadParameter("stage must be one of data|training|evaluation|deployment|monitoring")
    if type_value not in TYPES:
        raise typer.BadParameter("type must be one of model|evaluation_protocol|generic")
    if confidence_value not in RECONSTRUCTION_CONFIDENCE:
        raise typer.BadParameter("confidence must be one of low|medium|high")
    if not _validate_original_decision_date(original_date_value):
        raise typer.BadParameter('original-decision-date must be "unknown" or YYYY-MM-DD')

    evidence_values = _parse_list_text(evidence_text)
    if not evidence_values:
        typer.echo("FAIL BACKFILL_EVIDENCE_REQUIRED: At least one evidence ref is required.")
        raise typer.Exit(code=2)
    evidence_errors = _validate_evidence_refs(evidence_values)
    if evidence_errors:
        for error in evidence_errors:
            typer.echo(f"FAIL BACKFILL_INVALID_EVIDENCE: {error.message}")
        raise typer.Exit(code=2)

    sections = {
        "Context": _prompt_if_missing(context, "Context", "TODO"),
        "Decision": _prompt_if_missing(decision, "Decision", f"Backfilled decision: {title_value}"),
        "Rationale": _prompt_if_missing(rationale, "Rationale", "TODO: Confirm rationale from available evidence."),
        "Alternatives": _prompt_if_missing(alternatives, "Alternatives", "TODO: Reconstruct alternatives if known."),
        "Consequences": _prompt_if_missing(consequences, "Consequences", "TODO: Record observed consequences."),
    }

    try:
        next_id = _next_decision_id(decisions_dir)
        payload = {
            "id": next_id,
            "title": title_value,
            "status": "proposed",
            "type": type_value,
            "stage": stage_value,
            "date": str(date.today()),
            "owner": owner_value,
            "stakeholders": _parse_stakeholders_csv(stakeholders),
            "template_version": "1.0",
            "links": [_evidence_link_for_ref(ref, index) for index, ref in enumerate(evidence_values, start=1)],
            "reconstruction": {
                "mode": "backfill",
                "original_decision_date": original_date_value,
                "evidence_confidence": confidence_value,
                "evidence_sources": evidence_values,
                "known_gaps": _parse_list_text(known_gaps, separator=";"),
            },
        }
        payload.update(_template_payload(type_value))
        out_path = _write_decision_file(
            decisions_dir,
            payload,
            sections,
            {
                "Backfill Review Checklist": "\n".join(
                    [
                        "- [ ] Confirm original decision date or keep `unknown`",
                        "- [ ] Confirm evidence confidence",
                        "- [ ] Complete rationale",
                        "- [ ] Complete alternatives",
                        "- [ ] Complete consequences",
                        "- [ ] Review known gaps",
                        "- [ ] Decide whether status can move from proposed to accepted",
                    ]
                )
            },
        )
    except ValueError as exc:
        typer.echo(f"FAIL ID_RANGE_EXCEEDED: {exc}")
        raise typer.Exit(code=2)
    except OSError as exc:
        typer.echo(f"FAIL BACKFILL_IO_ERROR: {exc}")
        raise typer.Exit(code=2)

    typer.echo(f"Created {out_path.relative_to(resolved_root).as_posix()}")
    typer.echo("Review this proposed backfill record before changing status to accepted.")
    typer.echo("Validation may show TODO and checklist warnings until reconstruction is complete.")


def _load_records_for_command(root: Path):
    decisions_dir = root / "decisions"
    if not decisions_dir.is_dir():
        typer.echo(f"FAIL DECISIONS_DIR_MISSING: No decisions/ directory found at {root}. Run `dt init` first.")
        raise typer.Exit(code=2)
    return [_load_record(path) for path in sorted(decisions_dir.glob("DR-*.md"), key=lambda path: path.name)]


def _list_record_row(record) -> dict[str, object]:
    if record.parse_errors:
        message = record.parse_errors[0].message
        return {
            "id": str(record.yaml_id or ""),
            "status": "(parse error)",
            "type": "",
            "stage": "",
            "date": "",
            "owner": "",
            "title": message or "(parse error)",
            "parse_error": True,
            "parse_error_message": message or "(parse error)",
        }
    doc = record.doc if isinstance(record.doc, dict) else {}
    return {
        "id": str(doc.get("id") or record.yaml_id or ""),
        "status": str(doc.get("status") or ""),
        "type": str(doc.get("type") or ""),
        "stage": str(doc.get("stage") or ""),
        "date": str(doc.get("date") or ""),
        "owner": str(doc.get("owner") or ""),
        "title": str(doc.get("title") or ""),
        "parse_error": False,
        "parse_error_message": "",
    }


def list_command(
    status: Optional[str],
    decision_type: Optional[str],
    stage: Optional[str],
    output_format: str,
    root: Optional[Path],
) -> None:
    if status is not None and status not in {"proposed", "accepted", "rejected", "superseded", "deprecated"}:
        raise typer.BadParameter("status must be one of proposed|accepted|rejected|superseded|deprecated")
    if decision_type is not None and decision_type not in TYPES:
        raise typer.BadParameter("type must be one of model|evaluation_protocol|generic")
    if stage is not None and stage not in STAGES:
        raise typer.BadParameter("stage must be one of data|training|evaluation|deployment|monitoring")
    if output_format not in {"table", "json"}:
        raise typer.BadParameter("format must be one of table|json")

    resolved_root = _resolve_root(root)
    rows = [_list_record_row(record) for record in _load_records_for_command(resolved_root)]
    has_records = bool(rows)
    if status is not None:
        rows = [row for row in rows if row["parse_error"] or row["status"] == status]
    if decision_type is not None:
        rows = [row for row in rows if row["parse_error"] or row["type"] == decision_type]
    if stage is not None:
        rows = [row for row in rows if row["parse_error"] or row["stage"] == stage]

    if output_format == "json":
        typer.echo(json.dumps(rows, indent=2, sort_keys=True))
        return

    if not rows:
        if has_records:
            typer.echo("No decisions match the given filters.")
        else:
            typer.echo("No decisions found. Run `dt new ...` to create one.")
        return

    headers = ["ID", "STATUS", "TYPE", "STAGE", "DATE", "OWNER", "TITLE"]
    keys = ["id", "status", "type", "stage", "date", "owner", "title"]
    widths = {
        key: max(len(header), *(len(str(row[key])) for row in rows))
        for key, header in zip(keys, headers)
    }
    typer.echo("  ".join(header.ljust(widths[key]) for key, header in zip(keys, headers)))
    typer.echo("  ".join("-" * widths[key] for key in keys))
    for row in rows:
        typer.echo("  ".join(str(row[key]).ljust(widths[key]) for key in keys))


def _git_ignored(root: Path, path: str) -> bool:
    try:
        result = subprocess.run(["git", "-C", str(root), "check-ignore", "-q", path], capture_output=True, text=True)
    except FileNotFoundError:
        return False
    return result.returncode == 0


def _doctor_checks(root: Path) -> list[DoctorCheck]:
    checks = [DoctorCheck("package", "OK", f"decision-tracker {__version__}")]
    git_available = shutil.which("git") is not None
    checks.append(DoctorCheck("git", "OK" if git_available else "WARN", "Git executable found" if git_available else "Git executable not found"))
    git_root = _git_repo_root(root)
    checks.append(
        DoctorCheck(
            "git_repo",
            "OK" if git_root is not None else "WARN",
            f"Git repository detected at {git_root}" if git_root is not None else "No Git repository detected",
        )
    )
    decisions_dir = root / "decisions"
    checks.append(
        DoctorCheck(
            "decisions_dir",
            "OK" if decisions_dir.is_dir() else "FAIL",
            "decisions/ exists" if decisions_dir.is_dir() else "decisions/ is missing; run `dt init`",
        )
    )
    gitignore = root / ".gitignore"
    gitignore_text = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    has_block = GITIGNORE_START in gitignore_text and GITIGNORE_END in gitignore_text
    checks.append(
        DoctorCheck(
            "gitignore_block",
            "OK" if has_block else "WARN",
            "Decision Tracker .gitignore block present" if has_block else "Decision Tracker .gitignore block missing",
        )
    )
    workflow = root / ".github" / "workflows" / "pages.yml"
    checks.append(
        DoctorCheck(
            "pages_workflow",
            "OK" if workflow.exists() else "WARN",
            "GitHub Pages workflow present" if workflow.exists() else "GitHub Pages workflow missing",
        )
    )
    ignored_paths = ["_site/", "reports/", "decisions/index.json", "decisions/graph.json", "decisions/artifacts.json"]
    if git_root is None:
        checks.append(DoctorCheck("generated_outputs_ignored", "WARN", "Cannot verify ignored outputs outside a Git repository"))
    else:
        missing = [path for path in ignored_paths if not _git_ignored(root, path)]
        checks.append(
            DoctorCheck(
                "generated_outputs_ignored",
                "OK" if not missing else "WARN",
                "Generated outputs are ignored" if not missing else f"Generated outputs not ignored: {', '.join(missing)}",
            )
        )
    viewer_ready = all((Path(__file__).parent / "assets" / "viewer" / name).exists() for name in ("index.html", "app.js", "styles.css"))
    checks.append(
        DoctorCheck(
            "viewer_assets",
            "OK" if viewer_ready else "FAIL",
            "Packaged viewer assets available" if viewer_ready else "Packaged viewer assets are missing",
        )
    )
    return checks


def doctor_command(root: Optional[Path], output_format: str) -> None:
    if output_format not in {"text", "json"}:
        raise typer.BadParameter("format must be one of text|json")
    resolved_root = _resolve_root(root)
    checks = _doctor_checks(resolved_root)
    if output_format == "json":
        typer.echo(json.dumps([check.__dict__ for check in checks], indent=2, sort_keys=True))
    else:
        for check in checks:
            typer.echo(f"{check.status} {check.name}: {check.message}")
    raise typer.Exit(code=2 if any(check.status == "FAIL" for check in checks) else 0)


def validate_command(all_records: bool, decision_id: Optional[str], root: Optional[Path], strict: bool = False) -> None:
    resolved_root = _resolve_root(root)
    records = _load_records_for_command(resolved_root)
    context = _validation_context(records)
    git_root = _git_repo_root(resolved_root)

    if all_records or not decision_id:
        selected = records
    else:
        selected = [record for record in records if record.yaml_id == decision_id]
        if not selected:
            typer.echo(f"FAIL {decision_id}: YAML_MISSING_KEY: Decision id not found")
            raise typer.Exit(code=3)

    has_failures = False
    has_warnings = False
    for record in selected:
        errors, warnings, _ = _validation_messages(record, context, git_root, resolved_root)
        record_id = record.yaml_id or "UNKNOWN"
        if errors:
            has_failures = True
            for error in errors:
                typer.echo(f"FAIL {record_id}: {error.code}: {error.message}{_record_file_suffix(record.path, resolved_root)}")
        for warning in warnings:
            has_warnings = True
            typer.echo(f"WARN {record_id}: {warning.code}: {warning.message}{_record_file_suffix(record.path, resolved_root)}")
        if not errors:
            typer.echo(f"OK {record_id}")

    raise typer.Exit(code=3 if has_failures or (strict and has_warnings) else 0)


def new_command(
    title: str,
    stage: str,
    decision_type: str,
    owner: str,
    stakeholders: str,
    git_head: bool,
    root: Optional[Path],
) -> None:
    if stage not in STAGES:
        raise typer.BadParameter("stage must be one of data|training|evaluation|deployment|monitoring")
    if decision_type not in TYPES:
        raise typer.BadParameter("type must be one of model|evaluation_protocol|generic")

    resolved_root = _resolve_root(root)
    decisions_dir = resolved_root / "decisions"
    try:
        if not decisions_dir.is_dir():
            typer.echo(f"FAIL DECISIONS_DIR_MISSING: No decisions/ directory found at {resolved_root}. Run `dt init` first.")
            raise typer.Exit(code=2)
        next_id = _next_decision_id(decisions_dir)

        payload = {
            "id": next_id,
            "title": title,
            "status": "proposed",
            "type": decision_type,
            "stage": stage,
            "date": str(date.today()),
            "owner": owner,
            "stakeholders": _parse_stakeholders_csv(stakeholders),
            "template_version": "1.0",
            "links": [],
        }
        if git_head:
            try:
                head_sha = _resolve_git_head(resolved_root)
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
        payload.update(_template_payload(decision_type))

        out_path = _write_decision_file(
            decisions_dir,
            payload,
            {
                "Context": "TODO",
                "Decision": "TODO",
                "Rationale": "TODO",
                "Alternatives": "N/A",
                "Consequences": "TODO",
            },
        )
    except ValueError as exc:
        typer.echo(f"FAIL ID_RANGE_EXCEEDED: {exc}")
        raise typer.Exit(code=2)
    except OSError as exc:
        typer.echo(f"FAIL NEW_IO_ERROR: {exc}")
        raise typer.Exit(code=2)

    relative_path = out_path.relative_to(resolved_root).as_posix()
    typer.echo(f"Created {relative_path}")


DEFAULT_DISCOVER_KEYWORDS = ",".join(DISCOVER_KEYWORDS)
