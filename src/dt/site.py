from __future__ import annotations

import argparse
import csv
import html
import json
import os
import shutil
import subprocess
import sys
from importlib import resources
from io import StringIO
from pathlib import Path
from typing import Optional


VIEWER_CONFIG_PLACEHOLDER = "<script>\n      window.DT_VIEWER_CONFIG = window.DT_VIEWER_CONFIG || {};\n    </script>"
SITE_MARKER = "__DT_SITE__"
LEGACY_SITE_MARKER = ".decision-tracker-site"


def _run(command: list[str], root: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    return subprocess.run(command, cwd=root, capture_output=True, text=True, env=env)


def _copy_required(source: Path, target: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(f"Missing required file: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _viewer_asset_path(name: str) -> Path:
    return Path(str(resources.files("dt.assets.viewer").joinpath(name)))


def workflow_template() -> str:
    return resources.files("dt.assets.workflows").joinpath("pages.yml").read_text(encoding="utf-8")


def _git_value(root: Path, args: list[str]) -> str:
    try:
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _site_meta(root: Path) -> dict[str, str]:
    commit = os.environ.get("GITHUB_SHA") or _git_value(root, ["rev-parse", "--verify", "HEAD"])
    branch = os.environ.get("GITHUB_REF_NAME") or _git_value(root, ["branch", "--show-current"])
    return {
        "generated_from_commit": commit,
        "source_branch": branch,
    }


def _csv_rows(csv_text: str) -> list[dict[str, str]]:
    return [dict(row) for row in csv.DictReader(StringIO(csv_text))]


def _count_by(decisions: list[dict[str, object]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for decision in decisions:
        value = str(decision.get(key, ""))
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _average_score(decisions: list[dict[str, object]], key: str) -> float:
    values: list[float] = []
    for decision in decisions:
        scores = decision.get("scores")
        if isinstance(scores, dict):
            values.append(float(scores.get(key, 0)))
    return round(sum(values) / len(values), 3) if values else 0.0


def _format_number(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _short_commit(value: str) -> str:
    return value[:7] if value else "not available"


def _warning_lines(validation_output: str) -> list[str]:
    return [line for line in validation_output.splitlines() if line.startswith("WARN ")]


def _render_count_items(counts: dict[str, int]) -> str:
    return "\n".join(
        f'<div class="audit-row"><span>{html.escape(key)}</span><strong>{value}</strong></div>'
        for key, value in counts.items()
    )


def _as_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]


def _render_reconstruction_audit(decisions: list[dict[str, object]]) -> str:
    reconstructed = [decision for decision in decisions if isinstance(decision.get("reconstruction"), dict)]
    if not reconstructed:
        return (
            '<section class="report-section">'
            "<h2>Reconstructed Records</h2>"
            "<p>No backfilled or reconstructed records are present in this export.</p>"
            "</section>\n"
        )

    rows = []
    for decision in reconstructed:
        reconstruction = decision.get("reconstruction")
        assert isinstance(reconstruction, dict)
        evidence_sources = _as_string_list(reconstruction.get("evidence_sources"))
        known_gaps = _as_string_list(reconstruction.get("known_gaps"))
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(decision.get('id', '')))}</td>"
            f"<td>{html.escape(str(decision.get('title', '')))}</td>"
            f"<td>{html.escape(str(reconstruction.get('original_decision_date', 'unknown')))}</td>"
            f"<td>{html.escape(str(reconstruction.get('evidence_confidence', '')))}</td>"
            f"<td>{len(evidence_sources)}</td>"
            f"<td>{len(known_gaps)}</td>"
            "</tr>"
        )

    return (
        '<section class="report-section">'
        "<h2>Reconstructed Records</h2>"
        "<p>Backfilled records are reconstructed from historical evidence and should stay proposed until reviewed.</p>"
        '<div class="table-wrap"><table class="report-table">'
        "<thead><tr><th>ID</th><th>Decision</th><th>Original date</th><th>Confidence</th><th>Evidence</th><th>Known gaps</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table></div>"
        "</section>\n"
    )


def _render_review_audit(decisions: list[dict[str, object]]) -> str:
    counts: dict[str, int] = {}
    for decision in decisions:
        review = decision.get("review")
        if not isinstance(review, dict):
            continue
        status = str(review.get("status", ""))
        counts[status] = counts.get(status, 0) + 1
    if not counts:
        return ""
    return (
        '<section class="report-section">'
        "<h2>Review Status</h2>"
        "<p>Optional review metadata summarizes human audit state when records provide it.</p>"
        f"{_render_count_items(dict(sorted(counts.items())))}"
        "</section>\n"
    )


def _render_score_card(name: str, value: float, note: str) -> str:
    percent = max(0, min(100, int(round(value * 100))))
    return (
        '<article class="score-card">'
        f"<div><h3>{html.escape(name)}</h3><p>{html.escape(note)}</p></div>"
        f"<strong>{html.escape(_format_number(value))}</strong>"
        f'<div class="score-bar" aria-label="{html.escape(name)} score {percent}%">'
        f'<span style="width: {percent}%"></span>'
        "</div>"
        "</article>"
    )


def _render_report_html(
    decisions: list[dict[str, object]],
    metrics_csv: str,
    validation_output: str,
    site_meta: dict[str, str],
) -> str:
    metrics_rows = _csv_rows(metrics_csv)
    total = len(decisions)
    status_counts = _count_by(decisions, "status")
    accepted = status_counts.get("accepted", 0)
    proposed = status_counts.get("proposed", 0)
    superseded = status_counts.get("superseded", 0)
    link_total = sum(int(decision.get("link_count", 0)) for decision in decisions)
    artifact_refs = {
        link.get("target")
        for decision in decisions
        for link in decision.get("links", [])
        if isinstance(link, dict) and str(link.get("target", "")).startswith("artifact:")
    }
    warnings = _warning_lines(validation_output)
    reconstruction_audit = _render_reconstruction_audit(decisions)
    review_audit = _render_review_audit(decisions)

    avg_scores = {
        "Completeness": _average_score(decisions, "completeness"),
        "Connectedness": _average_score(decisions, "connectedness"),
        "Inclusiveness": _average_score(decisions, "inclusiveness"),
        "Traceability": _average_score(decisions, "traceability"),
    }
    smells = {
        "Alternatives marked N/A": sum(int(row.get("alternatives_is_na", 0)) for row in metrics_rows),
        "Weak traceability": sum(float(row.get("score_traceability", 0)) < 0.5 for row in metrics_rows),
        "No evidence link": sum(int(row.get("links_by_rel_supported_by", 0)) == 0 for row in metrics_rows),
    }
    attention_rows = sorted(
        metrics_rows,
        key=lambda row: (float(row.get("score_traceability", 0)), int(row.get("link_total", 0)), row.get("decision_id", "")),
    )[:5]

    score_cards = "\n".join(
        [
            _render_score_card("Completeness", avg_scores["Completeness"], "Required sections and core metadata are present."),
            _render_score_card(
                "Traceability",
                avg_scores["Traceability"],
                "Records are connected to evidence, implementation, evaluation, or superseded decisions.",
            ),
            _render_score_card("Connectedness", avg_scores["Connectedness"], "Records link to distinct artifacts and related decisions."),
            _render_score_card("Inclusiveness", avg_scores["Inclusiveness"], "Records identify owner and stakeholder coverage."),
        ]
    )
    warning_items = (
        "\n".join(f"<li>{html.escape(line)}</li>" for line in warnings)
        if warnings
        else "<li>No validation warnings were emitted.</li>"
    )
    smell_items = "\n".join(
        f'<div class="audit-row"><span>{html.escape(name)}</span><strong>{value}</strong></div>'
        for name, value in smells.items()
    )
    attention_items = "\n".join(
        "<tr>"
        f"<td>{html.escape(row.get('decision_id', ''))}</td>"
        f"<td>{html.escape(row.get('title', ''))}</td>"
        f"<td>{html.escape(row.get('status', ''))}</td>"
        f"<td>{html.escape(row.get('link_total', '0'))}</td>"
        f"<td>{html.escape(row.get('score_traceability', '0'))}</td>"
        "</tr>"
        for row in attention_rows
    )
    recent_items = "\n".join(
        f"<li><strong>{html.escape(str(decision.get('id', '')))}</strong> {html.escape(str(decision.get('title', '')))}</li>"
        for decision in sorted(decisions, key=lambda item: str(item.get("id", "")), reverse=True)[:4]
    )

    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "  <head>\n"
        '    <meta charset="utf-8" />\n'
        '    <meta name="viewport" content="width=device-width, initial-scale=1" />\n'
        "    <title>Decision Tracker Audit Report</title>\n"
        '    <link rel="stylesheet" href="./styles.css" />\n'
        "  </head>\n"
        "  <body>\n"
        '    <main class="report-page report-paper">\n'
        '      <nav class="report-actions" aria-label="Report actions">\n'
        '        <a class="back-link" href="./">Back to viewer</a>\n'
        '        <button class="print-button" type="button" onclick="window.print()">Print report</button>\n'
        "      </nav>\n"
        '      <article class="report-document">\n'
        '        <header class="report-cover">\n'
        '          <p class="eyebrow">Decision Tracker</p>\n'
        "          <h1>Decision Tracker Audit Report</h1>\n"
        "          <p>Executive summary and audit snapshot generated from repository decision records.</p>\n"
        '          <dl class="report-meta">\n'
        f"            <div><dt>Source branch</dt><dd>{html.escape(site_meta.get('source_branch') or 'not available')}</dd></div>\n"
        f"            <div><dt>Source commit</dt><dd>{html.escape(_short_commit(site_meta.get('generated_from_commit', '')))}</dd></div>\n"
        "            <div><dt>Data sources</dt><dd>index.json, metrics.csv, validation.txt</dd></div>\n"
        "          </dl>\n"
        "        </header>\n"
        '        <section class="executive-summary" aria-label="Executive summary">\n'
        "          <div>\n"
        "            <h2>Executive Summary</h2>\n"
        f"            <p>The repository contains <strong>{total}</strong> decision records with <strong>{link_total}</strong> trace links across <strong>{len(artifact_refs)}</strong> unique artifact references. <strong>{accepted}</strong> records are accepted, <strong>{proposed}</strong> are proposed, and <strong>{superseded}</strong> are superseded.</p>\n"
        f"            <p>The main audit signal is traceability: average traceability is <strong>{html.escape(_format_number(avg_scores['Traceability']))}</strong>, with <strong>{smells['Weak traceability']}</strong> records below the weak-traceability threshold.</p>\n"
        "          </div>\n"
        '          <div class="kpi-grid">\n'
        f'            <div class="kpi"><span>Total DRs</span><strong>{total}</strong></div>\n'
        f'            <div class="kpi"><span>Accepted</span><strong>{accepted}</strong></div>\n'
        f'            <div class="kpi"><span>Trace Links</span><strong>{link_total}</strong></div>\n'
        f'            <div class="kpi"><span>Warnings</span><strong>{len(warnings)}</strong></div>\n'
        "          </div>\n"
        "        </section>\n"
        '        <section class="report-section report-scores">\n'
        "          <h2>Quality Scores</h2>\n"
        '          <div class="score-grid">\n'
        f"{score_cards}\n"
        "          </div>\n"
        "        </section>\n"
        '        <section class="report-section audit-grid">\n'
        '          <article class="audit-panel">\n'
        "            <h2>Decision Coverage</h2>\n"
        "            <h3>By stage</h3>\n"
        f"{_render_count_items(_count_by(decisions, 'stage'))}\n"
        "            <h3>By type</h3>\n"
        f"{_render_count_items(_count_by(decisions, 'type'))}\n"
        "          </article>\n"
        '          <article class="audit-panel">\n'
        "            <h2>Status and Smells</h2>\n"
        "            <h3>By status</h3>\n"
        f"{_render_count_items(status_counts)}\n"
        "            <h3>Audit smells</h3>\n"
        f"{smell_items}\n"
        "          </article>\n"
        "        </section>\n"
        '        <section class="report-section">\n'
        "          <h2>Attention Items</h2>\n"
        "          <p>Records below are sorted by traceability score first. They are useful candidates for adding evidence, implementation, evaluation, or supersession links.</p>\n"
        '          <div class="table-wrap"><table class="report-table">\n'
        "            <thead><tr><th>ID</th><th>Decision</th><th>Status</th><th>Links</th><th>Traceability</th></tr></thead>\n"
        f"            <tbody>{attention_items}</tbody>\n"
        "          </table></div>\n"
        "        </section>\n"
        f"{reconstruction_audit}"
        f"{review_audit}"
        '        <section class="report-section audit-grid">\n'
        '          <article class="audit-panel">\n'
        "            <h2>Validation Notes</h2>\n"
        "            <ul>\n"
        f"{warning_items}\n"
        "            </ul>\n"
        "          </article>\n"
        '          <article class="audit-panel">\n'
        "            <h2>Recent Records</h2>\n"
        "            <ul>\n"
        f"{recent_items}\n"
        "            </ul>\n"
        "          </article>\n"
        "        </section>\n"
        '        <section class="report-section raw-artifacts">\n'
        "          <h2>Raw Artifacts</h2>\n"
        "          <p>The report page is a rendered view only. The canonical generated files are preserved for inspection and downstream use.</p>\n"
        '          <div class="artifact-links">\n'
        '            <a href="data/report.md">Markdown report</a>\n'
        '            <a href="data/metrics.csv">Metrics CSV</a>\n'
        '            <a href="data/index.json">Decision index JSON</a>\n'
        '            <a href="data/graph.json">Graph JSON</a>\n'
        '            <a href="data/artifacts.json">Artifacts JSON</a>\n'
        '            <a href="data/validation.txt">Validation log</a>\n'
        "          </div>\n"
        "        </section>\n"
        "      </article>\n"
        "    </main>\n"
        "  </body>\n"
        "</html>\n"
    )


def _is_safe_existing_site_dir(site_dir: Path) -> bool:
    if not site_dir.exists():
        return True
    if not site_dir.is_dir():
        return False
    if not any(site_dir.iterdir()):
        return True
    if (site_dir / SITE_MARKER).exists() or (site_dir / LEGACY_SITE_MARKER).exists():
        return True
    return site_dir.name == "_site" and (site_dir / "index.html").exists() and (site_dir / "data").is_dir()


def _preflight_site_output(site_dir: Path, force: bool) -> None:
    if site_dir.is_symlink() and not force:
        return
    if site_dir.exists():
        probe_dir = site_dir if site_dir.is_dir() else site_dir.parent
    else:
        probe_dir = site_dir.parent
        while not probe_dir.exists() and probe_dir != probe_dir.parent:
            probe_dir = probe_dir.parent
    probe = probe_dir / ".dt-write-test"
    try:
        probe_dir.mkdir(parents=True, exist_ok=True)
        probe.write_text("ok\n", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        raise OSError(f"Cannot write site output at {site_dir}: {exc}") from exc


def _guard_site_dir(root: Path, site_dir: Path, force: bool) -> None:
    if site_dir.is_symlink() and not force:
        sys.stderr.write(
            f"FAIL SITE_DIR_UNSAFE: Refusing to write through symlinked site output path: {site_dir}. "
            "Re-run with --force to replace the symlink.\n"
        )
        raise SystemExit(2)
    if site_dir == root or root.is_relative_to(site_dir):
        sys.stderr.write(f"FAIL SITE_DIR_UNSAFE: Refusing to replace project root or ancestor: {site_dir}\n")
        raise SystemExit(2)
    if site_dir.exists() and not site_dir.is_dir():
        sys.stderr.write(f"FAIL SITE_DIR_UNSAFE: Site output path is not a directory: {site_dir}\n")
        raise SystemExit(2)
    if site_dir.exists() and any(site_dir.iterdir()) and not force and not _is_safe_existing_site_dir(site_dir):
        sys.stderr.write(
            "FAIL SITE_DIR_NOT_EMPTY: Refusing to replace a non-empty directory that does not look "
            f"like a Decision Tracker site: {site_dir}. Re-run with --force to replace it.\n"
        )
        raise SystemExit(2)
    _preflight_site_output(site_dir, force)


def build_site(root: Path, site_dir: Path, viewer_dir: Optional[Path] = None, force: bool = False) -> None:
    try:
        _guard_site_dir(root, site_dir, force)
    except OSError as exc:
        sys.stderr.write(f"FAIL BUILD_SITE_IO_ERROR: {exc}\n")
        raise SystemExit(2)

    validate = _run([sys.executable, "-m", "dt.cli", "validate", "--all", "--root", str(root)], root)
    validation_output = validate.stdout
    if validate.stderr:
        validation_output += validate.stderr
    if validate.returncode != 0:
        sys.stderr.write(validation_output)
        raise SystemExit(validate.returncode)

    report = _run([sys.executable, "-m", "dt.cli", "report", "--root", str(root)], root)
    if report.stdout:
        sys.stdout.write(report.stdout)
    if report.stderr:
        sys.stderr.write(report.stderr)
    if report.returncode != 0:
        raise SystemExit(report.returncode)

    try:
        if site_dir.is_symlink():
            site_dir.unlink()
        elif site_dir.exists():
            shutil.rmtree(site_dir)
        data_dir = site_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        (site_dir / SITE_MARKER).write_text("Generated by Decision Tracker. Safe to replace.\n", encoding="utf-8")

        asset_root = viewer_dir
        _copy_required(asset_root / "app.js" if asset_root else _viewer_asset_path("app.js"), site_dir / "app.js")
        _copy_required(asset_root / "styles.css" if asset_root else _viewer_asset_path("styles.css"), site_dir / "styles.css")

        index_source = asset_root / "index.html" if asset_root else _viewer_asset_path("index.html")
        index_html = index_source.read_text(encoding="utf-8")
        config = (
            "<script>\n"
            "      window.DT_VIEWER_CONFIG = {\n"
            '        dataBase: "data",\n'
            '        metaPath: "data/site-meta.json",\n'
            '        reportPath: "report.html",\n'
            '        validationPath: "data/validation.txt",\n'
            "      };\n"
            "    </script>"
        )
        if VIEWER_CONFIG_PLACEHOLDER not in index_html:
            raise RuntimeError("viewer asset index.html is missing the DT_VIEWER_CONFIG placeholder")
        index_html = index_html.replace(VIEWER_CONFIG_PLACEHOLDER, config)
        (site_dir / "index.html").write_text(index_html, encoding="utf-8")

        for name in ("index.json", "graph.json", "artifacts.json"):
            _copy_required(root / "decisions" / name, data_dir / name)
        report_path = root / "reports" / "report.md"
        metrics_path = root / "reports" / "metrics.csv"
        _copy_required(report_path, data_dir / "report.md")
        _copy_required(metrics_path, data_dir / "metrics.csv")
        (data_dir / "validation.txt").write_text(validation_output, encoding="utf-8")
        site_meta = _site_meta(root)
        (data_dir / "site-meta.json").write_text(json.dumps(site_meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (site_dir / "report.html").write_text(
            _render_report_html(
                json.loads((root / "decisions" / "index.json").read_text(encoding="utf-8")),
                metrics_path.read_text(encoding="utf-8"),
                validation_output,
                site_meta,
            ),
            encoding="utf-8",
        )
    except OSError as exc:
        sys.stderr.write(f"FAIL BUILD_SITE_IO_ERROR: {exc}\n")
        raise SystemExit(2)

    print(f"Built static viewer site at {site_dir.relative_to(root) if site_dir.is_relative_to(root) else site_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the static Decision Tracker viewer site.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root.")
    parser.add_argument("--site-dir", type=Path, default=None, help="Output directory. Defaults to ROOT/_site.")
    parser.add_argument("--viewer-dir", type=Path, default=None, help="Optional viewer asset directory for development/testing.")
    parser.add_argument("--force", action="store_true", help="Replace a non-empty output directory.")
    args = parser.parse_args()

    root = args.root.resolve()
    site_dir = args.site_dir.absolute() if args.site_dir else root / "_site"
    viewer_dir = args.viewer_dir.resolve() if args.viewer_dir else None
    build_site(root, site_dir, viewer_dir, args.force)


if __name__ == "__main__":
    main()
