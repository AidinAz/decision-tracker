from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import typer
import yaml

from dt.constants import ARTIFACT_KINDS, CORE_HEADINGS, RELS, REQUIRED_HEADINGS
from dt.git import _git_repo_root
from dt.markdown import _extract_front_matter, _parse_headings
from dt.models import DecisionComputed
from dt.paths import _json_dump
from dt.refs import _infer_target_id, _ref_is_valid
from dt.utils import _is_non_empty_section, _is_non_empty_string, _record_file_suffix, _round3, _stable_stakeholders
from dt.validation import _load_record, _validation_context, _validation_messages, _yaml_valid


def _clean_stale_outputs(root: Path) -> None:
    for name in ("index.json", "graph.json", "artifacts.json"):
        path = root / "decisions" / name
        if path.exists():
            path.unlink()
    reports_dir = root / "reports"
    for name in ("metrics.csv", "report.md"):
        path = reports_dir / name
        if path.exists():
            path.unlink()


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
    content_score = non_empty_core / len(CORE_HEADINGS)
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


def generate_report(root: Path) -> None:
    decisions_dir = root / "decisions"
    if not decisions_dir.is_dir():
        typer.echo(f"FAIL DECISIONS_DIR_MISSING: No decisions/ directory found at {root}. Run `dt init` first.")
        raise typer.Exit(code=2)

    _clean_stale_outputs(root)
    files = sorted(decisions_dir.glob("DR-*.md"), key=lambda path: path.name)
    loaded_records = [_load_record(path) for path in files]
    context = _validation_context(loaded_records)
    git_root = _git_repo_root(root)

    has_validation_failures = False
    for record in loaded_records:
        errors, warnings, _ = _validation_messages(record, context, git_root, root)
        record_id = record.yaml_id or "UNKNOWN"
        for error in errors:
            has_validation_failures = True
            typer.echo(f"FAIL {record_id}: {error.code}: {error.message}{_record_file_suffix(record.path, root)}")
        for warning in warnings:
            typer.echo(f"WARN {record_id}: {warning.code}: {warning.message}{_record_file_suffix(record.path, root)}")
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
    reconstructed_records: list[dict[str, Any]] = []
    review_counts: dict[str, int] = {}

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
        if isinstance(doc.get("reconstruction"), dict):
            reconstructed_records.append(
                {
                    "id": decision_id,
                    "title": str(doc["title"]),
                    "confidence": str(doc["reconstruction"].get("evidence_confidence", "")),
                    "known_gaps": len(doc["reconstruction"].get("known_gaps", []) or []),
                }
            )
        if isinstance(doc.get("review"), dict):
            review_status = str(doc["review"].get("status", ""))
            review_counts[review_status] = review_counts.get(review_status, 0) + 1

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

        index_entry = {
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
        if isinstance(doc.get("reconstruction"), dict):
            index_entry["reconstruction"] = doc["reconstruction"]
        if isinstance(doc.get("review"), dict):
            index_entry["review"] = doc["review"]
        index_payload.append(index_entry)

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

    attention_rows = sorted(
        csv_rows,
        key=lambda row: (
            float(row["score_traceability"]),
            int(row["link_total"]),
            str(row["decision_id"]),
        ),
    )[:5]

    report_lines = [
        "# Decision Tracker Report",
        "## Executive summary",
        f"- total decisions: {total}",
        f"- total trace links: {sum(int(row['link_total']) for row in csv_rows)}",
        f"- accepted decisions: {status_counts.get('accepted', 0)}",
        f"- proposed decisions: {status_counts.get('proposed', 0)}",
        f"- superseded decisions: {status_counts.get('superseded', 0)}",
        f"- weak traceability records: {smell_weak_trace}",
        "",
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
            "",
            "## Attention items",
        ]
    )
    if attention_rows:
        for row in attention_rows:
            report_lines.append(
                f"- {row['decision_id']}: {row['title']} "
                f"(status={row['status']}, links={row['link_total']}, traceability={row['score_traceability']})"
            )
    else:
        report_lines.append("- none")
    report_lines.extend(["", "## Reconstructed records"])
    if reconstructed_records:
        for record in sorted(reconstructed_records, key=lambda item: str(item["id"])):
            report_lines.append(
                f"- {record['id']}: {record['title']} "
                f"(confidence={record['confidence']}, known_gaps={record['known_gaps']})"
            )
    else:
        report_lines.append("- none")
    if review_counts:
        report_lines.extend(["", "## Review status"])
        for key in sorted(review_counts):
            report_lines.append(f"- {key}: {review_counts[key]}")

    report_path = root / "reports" / "report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    typer.echo(
        "Generated decisions/index.json, decisions/graph.json, decisions/artifacts.json, reports/metrics.csv, reports/report.md"
    )
