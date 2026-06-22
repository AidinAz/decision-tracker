import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dt.cli import app
from dt.git import GitCommitCheck
from dt.validation import _yaml_valid


def _prepare_workdir(tmp_path: Path) -> Path:
    repo = Path(__file__).resolve().parents[1]
    fixtures = repo / "fixtures" / "decisions"

    work = tmp_path / "work"
    work.mkdir()
    decisions_dir = work / "decisions"
    decisions_dir.mkdir()
    for path in fixtures.glob("*.md"):
        shutil.copy2(path, decisions_dir / path.name)
    return work


def _run_git_or_skip(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    except FileNotFoundError:
        pytest.skip("git is not available")
    if result.returncode != 0 and args[:1] == ["--version"]:
        pytest.skip("git is not available")
    assert result.returncode == 0, result.stderr
    return result


def test_validate_fails_on_invalid_enum(tmp_path: Path):
    work = _prepare_workdir(tmp_path)
    target = next((work / "decisions").glob("DR-0001-*.md"))
    text = target.read_text(encoding="utf-8").splitlines()
    text = ["stage: foo" if line.startswith("stage: ") else line for line in text]
    target.write_text("\n".join(text) + "\n", encoding="utf-8")

    result = subprocess.run(["dt", "validate", "--all"], cwd=work, capture_output=True, text=True)
    assert result.returncode == 3
    assert "ENUM_INVALID" in (result.stdout + result.stderr)


def test_validate_rejects_invalid_calendar_date(tmp_path: Path):
    work = _prepare_workdir(tmp_path)
    target = next((work / "decisions").glob("DR-0001-*.md"))
    text = target.read_text(encoding="utf-8").splitlines()
    text = ["date: '2026-02-30'" if line.startswith("date: ") else line for line in text]
    target.write_text("\n".join(text) + "\n", encoding="utf-8")

    result = subprocess.run(["dt", "validate", "--all"], cwd=work, capture_output=True, text=True)
    assert result.returncode == 3
    assert "date must be a real calendar date" in result.stdout


def test_validate_explains_unquoted_yaml_scalars(tmp_path: Path):
    work = _prepare_workdir(tmp_path)
    target = next((work / "decisions").glob("DR-0001-*.md"))
    text = target.read_text(encoding="utf-8").splitlines()
    text = [
        "date: 2026-03-14" if line.startswith("date: ") else "template_version: 1.0" if line.startswith("template_version: ") else line
        for line in text
    ]
    target.write_text("\n".join(text) + "\n", encoding="utf-8")

    result = subprocess.run(["dt", "validate", "--all"], cwd=work, capture_output=True, text=True)
    assert result.returncode == 3
    assert "date must be a quoted string" in result.stdout
    assert "template_version must be the quoted string" in result.stdout


def test_validate_rejects_non_fixed_width_id(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    decisions_dir = work / "decisions"
    decisions_dir.mkdir()
    path = decisions_dir / "DR-7-short.md"
    path.write_text(
        "---\n"
        "id: DR-7\n"
        "title: Bad id\n"
        "status: proposed\n"
        "type: generic\n"
        "stage: data\n"
        "date: '2026-03-14'\n"
        "owner: ahmet\n"
        "stakeholders: []\n"
        "template_version: '1.0'\n"
        "links: []\n"
        "---\n"
        "\n"
        "## Context\nx\n\n## Decision\nx\n\n## Rationale\nx\n\n## Alternatives\nN/A\n\n## Consequences\nx\n",
        encoding="utf-8",
    )

    result = subprocess.run(["dt", "validate", "--all"], cwd=work, capture_output=True, text=True)
    assert result.returncode == 3
    assert "ID_FORMAT_INVALID" in result.stdout


def test_validate_rejects_duplicate_yaml_ids(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    decisions_dir = work / "decisions"
    decisions_dir.mkdir()
    for filename, title in [("DR-0001-a.md", "First"), ("DR-0002-b.md", "Second")]:
        (decisions_dir / filename).write_text(
            "---\n"
            "id: DR-0001\n"
            f"title: {title}\n"
            "status: proposed\n"
            "type: generic\n"
            "stage: data\n"
            "date: '2026-03-14'\n"
            "owner: ahmet\n"
            "stakeholders: []\n"
            "template_version: '1.0'\n"
            "links: []\n"
            "---\n"
            "\n"
            "## Context\nx\n\n## Decision\nx\n\n## Rationale\nx\n\n## Alternatives\nN/A\n\n## Consequences\nx\n",
            encoding="utf-8",
        )

    result = subprocess.run(["dt", "validate", "--all"], cwd=work, capture_output=True, text=True)
    assert result.returncode == 3
    assert result.stdout.count("ID_DUPLICATE") == 2
    assert "decisions/DR-0001-a.md" in result.stdout
    assert "decisions/DR-0002-b.md" in result.stdout


def test_validate_warns_on_todo_sections_without_failing(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    decisions_dir = work / "decisions"
    decisions_dir.mkdir()
    (decisions_dir / "DR-0001-draft.md").write_text(
        "---\n"
        "id: DR-0001\n"
        "title: Draft decision\n"
        "status: proposed\n"
        "type: generic\n"
        "stage: data\n"
        "date: '2026-03-14'\n"
        "owner: ahmet\n"
        "stakeholders: []\n"
        "template_version: '1.0'\n"
        "links: []\n"
        "---\n"
        "\n"
        "## Context\nTODO\n\n## Decision\nTODO: decide later\n\n## Rationale\nTODO finalize this section\n\n## Alternatives\nx\n\n## Consequences\nx\n",
        encoding="utf-8",
    )

    result = subprocess.run(["dt", "validate", "--all"], cwd=work, capture_output=True, text=True)

    assert result.returncode == 0
    assert "WARN DR-0001: TODO_SECTION: Section still contains TODO placeholder: ## Context" in result.stdout
    assert "WARN DR-0001: TODO_SECTION: Section still contains TODO placeholder: ## Decision" in result.stdout
    assert "WARN DR-0001: TODO_SECTION: Section still contains TODO placeholder: ## Rationale" in result.stdout
    assert "decisions/DR-0001-draft.md" in result.stdout
    assert "OK DR-0001" in result.stdout


def test_validate_strict_fails_on_warnings(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    decisions_dir = work / "decisions"
    decisions_dir.mkdir()
    (decisions_dir / "DR-0001-draft.md").write_text(
        "---\n"
        "id: DR-0001\n"
        "title: Draft decision\n"
        "status: proposed\n"
        "type: generic\n"
        "stage: data\n"
        "date: '2026-03-14'\n"
        "owner: ahmet\n"
        "stakeholders: []\n"
        "template_version: '1.0'\n"
        "links: []\n"
        "---\n"
        "\n"
        "## Context\nTODO\n\n## Decision\nx\n\n## Rationale\nx\n\n## Alternatives\nx\n\n## Consequences\nx\n",
        encoding="utf-8",
    )

    normal = subprocess.run(["dt", "validate", "--all"], cwd=work, capture_output=True, text=True)
    strict = subprocess.run(["dt", "validate", "--all", "--strict"], cwd=work, capture_output=True, text=True)
    alias = subprocess.run(["dt", "validate", "--all", "--fail-on-warn"], cwd=work, capture_output=True, text=True)

    assert normal.returncode == 0
    assert strict.returncode == 3
    assert alias.returncode == 3
    assert strict.stdout == normal.stdout


def test_validate_warns_on_missing_local_path_refs(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    decisions_dir = work / "decisions"
    decisions_dir.mkdir()
    (work / "docs").mkdir()
    (work / "docs" / "exists.md").write_text("ok\n", encoding="utf-8")
    (decisions_dir / "DR-0001-paths.md").write_text(
        "---\n"
        "id: DR-0001\n"
        "title: Path refs\n"
        "status: accepted\n"
        "type: generic\n"
        "stage: data\n"
        "date: '2026-03-14'\n"
        "owner: ahmet\n"
        "stakeholders: []\n"
        "template_version: '1.0'\n"
        "links:\n"
        "  - id: L-0001\n"
        "    rel: supported_by\n"
        "    artifact_kind: document\n"
        "    ref: path:docs/exists.md\n"
        "  - id: L-0002\n"
        "    rel: supported_by\n"
        "    artifact_kind: document\n"
        "    ref: path:docs/missing.md\n"
        "---\n"
        "\n"
        "## Context\nx\n\n## Decision\nx\n\n## Rationale\nx\n\n## Alternatives\nx\n\n## Consequences\nx\n",
        encoding="utf-8",
    )

    result = subprocess.run(["dt", "validate", "--all"], cwd=work, capture_output=True, text=True)
    strict = subprocess.run(["dt", "validate", "--all", "--strict"], cwd=work, capture_output=True, text=True)

    assert result.returncode == 0
    assert "PATH_REF_NOT_FOUND" in result.stdout
    assert "path:docs/missing.md" in result.stdout
    assert "path:docs/exists.md" not in result.stdout
    assert strict.returncode == 3


def test_validate_warns_on_non_portable_path_refs(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    decisions_dir = work / "decisions"
    decisions_dir.mkdir()
    (decisions_dir / "DR-0001-paths.md").write_text(
        "---\n"
        "id: DR-0001\n"
        "title: Path refs\n"
        "status: accepted\n"
        "type: generic\n"
        "stage: data\n"
        "date: '2026-03-14'\n"
        "owner: ahmet\n"
        "stakeholders: []\n"
        "template_version: '1.0'\n"
        "links:\n"
        "  - id: L-0001\n"
        "    rel: supported_by\n"
        "    artifact_kind: document\n"
        "    ref: path:/Users/me/private-notes.md\n"
        "  - id: L-0002\n"
        "    rel: supported_by\n"
        "    artifact_kind: document\n"
        "    ref: path:../outside.md\n"
        "---\n"
        "\n"
        "## Context\nx\n\n## Decision\nx\n\n## Rationale\nx\n\n## Alternatives\nx\n\n## Consequences\nx\n",
        encoding="utf-8",
    )

    result = subprocess.run(["dt", "validate", "--all"], cwd=work, capture_output=True, text=True)
    strict = subprocess.run(["dt", "validate", "--all", "--strict"], cwd=work, capture_output=True, text=True)

    assert result.returncode == 0
    assert result.stdout.count("PATH_REF_NOT_PORTABLE") == 2
    assert "uses an absolute or parent-relative path" in result.stdout
    assert "traceability across machines" in result.stdout
    assert "path:/Users/me/private-notes.md" in result.stdout
    assert "path:../outside.md" in result.stdout
    assert "PATH_REF_NOT_FOUND" not in result.stdout
    assert strict.returncode == 3


def test_validate_warns_on_incomplete_backfill_checklist(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    decisions_dir = work / "decisions"
    decisions_dir.mkdir()
    (decisions_dir / "DR-0001-backfill.md").write_text(
        "---\n"
        "id: DR-0001\n"
        "title: Backfill\n"
        "status: proposed\n"
        "type: generic\n"
        "stage: data\n"
        "date: '2026-03-14'\n"
        "owner: ahmet\n"
        "stakeholders: []\n"
        "template_version: '1.0'\n"
        "links: []\n"
        "reconstruction:\n"
        "  mode: backfill\n"
        "  original_decision_date: unknown\n"
        "  evidence_confidence: medium\n"
        "  evidence_sources:\n"
        "    - path:docs/notes.md\n"
        "  known_gaps: []\n"
        "---\n"
        "\n"
        "## Context\nx\n\n## Decision\nx\n\n## Rationale\nx\n\n## Alternatives\nx\n\n## Consequences\nx\n\n"
        "## Backfill Review Checklist\n- [ ] Complete rationale\n",
        encoding="utf-8",
    )

    result = subprocess.run(["dt", "validate", "--all"], cwd=work, capture_output=True, text=True)

    assert result.returncode == 0
    assert "BACKFILL_CHECKLIST_INCOMPLETE" in result.stdout


def test_validate_accepts_completed_backfill_checklist(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    decisions_dir = work / "decisions"
    decisions_dir.mkdir()
    (decisions_dir / "DR-0001-backfill.md").write_text(
        "---\n"
        "id: DR-0001\n"
        "title: Backfill\n"
        "status: proposed\n"
        "type: generic\n"
        "stage: data\n"
        "date: '2026-03-14'\n"
        "owner: ahmet\n"
        "stakeholders: []\n"
        "template_version: '1.0'\n"
        "links: []\n"
        "reconstruction:\n"
        "  mode: backfill\n"
        "  original_decision_date: unknown\n"
        "  evidence_confidence: medium\n"
        "  evidence_sources:\n"
        "    - path:docs/notes.md\n"
        "  known_gaps: []\n"
        "---\n"
        "\n"
        "## Context\nx\n\n## Decision\nx\n\n## Rationale\nx\n\n## Alternatives\nx\n\n## Consequences\nx\n\n"
        "## Backfill Review Checklist\n- [x] Complete rationale\n",
        encoding="utf-8",
    )

    result = subprocess.run(["dt", "validate", "--all"], cwd=work, capture_output=True, text=True)

    assert result.returncode == 0
    assert "BACKFILL_CHECKLIST_INCOMPLETE" not in result.stdout


def test_validate_optional_review_metadata(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    decisions_dir = work / "decisions"
    decisions_dir.mkdir()
    (decisions_dir / "DR-0001-review.md").write_text(
        "---\n"
        "id: DR-0001\n"
        "title: Review metadata\n"
        "status: proposed\n"
        "type: generic\n"
        "stage: data\n"
        "date: '2026-03-14'\n"
        "owner: ahmet\n"
        "stakeholders: []\n"
        "template_version: '1.0'\n"
        "links: []\n"
        "review:\n"
        "  status: reviewed\n"
        "  reviewed_by: [advisor]\n"
        "  reviewed_date: '2026-03-15'\n"
        "  notes: Looks complete\n"
        "---\n"
        "\n"
        "## Context\nx\n\n## Decision\nx\n\n## Rationale\nx\n\n## Alternatives\nx\n\n## Consequences\nx\n",
        encoding="utf-8",
    )

    result = subprocess.run(["dt", "validate", "--all"], cwd=work, capture_output=True, text=True)

    assert result.returncode == 0
    assert "OK DR-0001" in result.stdout


def test_validate_warns_on_incomplete_review_metadata(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    decisions_dir = work / "decisions"
    decisions_dir.mkdir()
    (decisions_dir / "DR-0001-review.md").write_text(
        "---\n"
        "id: DR-0001\n"
        "title: Review metadata\n"
        "status: proposed\n"
        "type: generic\n"
        "stage: data\n"
        "date: '2026-03-14'\n"
        "owner: ahmet\n"
        "stakeholders: []\n"
        "template_version: '1.0'\n"
        "links: []\n"
        "review:\n"
        "  status: reviewed\n"
        "  reviewed_by: []\n"
        "  reviewed_date: unknown\n"
        "  notes: Reviewed later\n"
        "---\n"
        "\n"
        "## Context\nx\n\n## Decision\nx\n\n## Rationale\nx\n\n## Alternatives\nx\n\n## Consequences\nx\n",
        encoding="utf-8",
    )

    result = subprocess.run(["dt", "validate", "--all"], cwd=work, capture_output=True, text=True)
    strict = subprocess.run(["dt", "validate", "--all", "--strict"], cwd=work, capture_output=True, text=True)

    assert result.returncode == 0
    assert result.stdout.count("REVIEW_INCOMPLETE") == 2
    assert "at least one reviewer" in result.stdout
    assert "reviewed_date" in result.stdout
    assert strict.returncode == 3


def test_validate_warns_on_changes_requested_without_notes(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    decisions_dir = work / "decisions"
    decisions_dir.mkdir()
    (decisions_dir / "DR-0001-review.md").write_text(
        "---\n"
        "id: DR-0001\n"
        "title: Review metadata\n"
        "status: proposed\n"
        "type: generic\n"
        "stage: data\n"
        "date: '2026-03-14'\n"
        "owner: ahmet\n"
        "stakeholders: []\n"
        "template_version: '1.0'\n"
        "links: []\n"
        "review:\n"
        "  status: changes_requested\n"
        "  reviewed_by: [advisor]\n"
        "  reviewed_date: '2026-03-15'\n"
        "  notes: '   '\n"
        "---\n"
        "\n"
        "## Context\nx\n\n## Decision\nx\n\n## Rationale\nx\n\n## Alternatives\nx\n\n## Consequences\nx\n",
        encoding="utf-8",
    )

    result = subprocess.run(["dt", "validate", "--all"], cwd=work, capture_output=True, text=True)

    assert result.returncode == 0
    assert "REVIEW_INCOMPLETE" in result.stdout
    assert "should include notes" in result.stdout


def test_validate_rejects_invalid_review_metadata(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    decisions_dir = work / "decisions"
    decisions_dir.mkdir()
    (decisions_dir / "DR-0001-review.md").write_text(
        "---\n"
        "id: DR-0001\n"
        "title: Review metadata\n"
        "status: proposed\n"
        "type: generic\n"
        "stage: data\n"
        "date: '2026-03-14'\n"
        "owner: ahmet\n"
        "stakeholders: []\n"
        "template_version: '1.0'\n"
        "links: []\n"
        "review:\n"
        "  status: done\n"
        "  reviewed_by: advisor\n"
        "  reviewed_date: '2026-02-30'\n"
        "  notes: 123\n"
        "---\n"
        "\n"
        "## Context\nx\n\n## Decision\nx\n\n## Rationale\nx\n\n## Alternatives\nx\n\n## Consequences\nx\n",
        encoding="utf-8",
    )

    result = subprocess.run(["dt", "validate", "--all"], cwd=work, capture_output=True, text=True)

    assert result.returncode == 3
    assert result.stdout.count("REVIEW_INVALID") == 4


def test_yaml_valid_rejects_invalid_review_metadata():
    doc = {
        "id": "DR-0001",
        "title": "Review metadata",
        "status": "proposed",
        "type": "generic",
        "stage": "data",
        "date": "2026-03-14",
        "owner": "ahmet",
        "stakeholders": [],
        "template_version": "1.0",
        "links": [],
        "review": {
            "status": "done",
            "reviewed_by": "advisor",
            "reviewed_date": "2026-02-30",
            "notes": 123,
        },
    }

    assert _yaml_valid(doc) is False


def test_validate_requires_model_spec_fields(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    decisions_dir = work / "decisions"
    decisions_dir.mkdir()
    path = decisions_dir / "DR-0001-model.md"
    path.write_text(
        "---\n"
        "id: DR-0001\n"
        "title: Missing model spec\n"
        "status: accepted\n"
        "type: model\n"
        "stage: training\n"
        "date: '2026-03-14'\n"
        "owner: ahmet\n"
        "stakeholders: [reviewer]\n"
        "template_version: '1.0'\n"
        "links:\n"
        "  - id: L-0001\n"
        "    rel: implements\n"
        "    artifact_kind: code\n"
        "    ref: git:commit:abc123\n"
        "  - id: L-0002\n"
        "    rel: supported_by\n"
        "    artifact_kind: document\n"
        "    ref: path:docs/model.md\n"
        "---\n"
        "\n"
        "## Context\nx\n\n## Decision\nx\n\n## Rationale\nx\n\n## Alternatives\nN/A\n\n## Consequences\nx\n",
        encoding="utf-8",
    )

    result = subprocess.run(["dt", "validate", "--all"], cwd=work, capture_output=True, text=True)
    assert result.returncode == 3
    assert "TEMPLATE_FIELD_MISSING" in result.stdout


def test_validate_requires_eval_spec_fields(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    decisions_dir = work / "decisions"
    decisions_dir.mkdir()
    path = decisions_dir / "DR-0001-eval.md"
    path.write_text(
        "---\n"
        "id: DR-0001\n"
        "title: Missing eval spec fields\n"
        "status: accepted\n"
        "type: evaluation_protocol\n"
        "stage: evaluation\n"
        "date: '2026-03-14'\n"
        "owner: ahmet\n"
        "stakeholders: [reviewer]\n"
        "template_version: '1.0'\n"
        "eval_spec:\n"
        "  protocol: fixed split\n"
        "  metrics:\n"
        "    - name: F1\n"
        "      threshold: '>= 0.7'\n"
        "  baseline:\n"
        "    ref: run:baseline\n"
        "    description: previous run\n"
        "links:\n"
        "  - id: L-0001\n"
        "    rel: supported_by\n"
        "    artifact_kind: data\n"
        "    ref: dvc:abc123\n"
        "  - id: L-0002\n"
        "    rel: evaluated_by\n"
        "    artifact_kind: experiment_run\n"
        "    ref: run:eval-1\n"
        "---\n"
        "\n"
        "## Context\nx\n\n## Decision\nx\n\n## Rationale\nx\n\n## Alternatives\nN/A\n\n## Consequences\nx\n",
        encoding="utf-8",
    )

    result = subprocess.run(["dt", "validate", "--all"], cwd=work, capture_output=True, text=True)
    assert result.returncode == 3
    assert "TEMPLATE_FIELD_MISSING" in result.stdout
    assert "eval_spec.dataset_ref" in result.stdout


def test_validate_reports_duplicate_heading_with_contract_code(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    decisions_dir = work / "decisions"
    decisions_dir.mkdir()
    path = decisions_dir / "DR-0001-dup.md"
    path.write_text(
        "---\n"
        "id: DR-0001\n"
        "title: Duplicate heading\n"
        "status: proposed\n"
        "type: generic\n"
        "stage: data\n"
        "date: '2026-03-14'\n"
        "owner: ahmet\n"
        "stakeholders: []\n"
        "template_version: '1.0'\n"
        "links: []\n"
        "---\n"
        "\n"
        "## Context\nx\n\n## Context\ny\n\n## Decision\nx\n\n## Rationale\nx\n\n## Alternatives\nN/A\n\n## Consequences\nx\n",
        encoding="utf-8",
    )

    result = subprocess.run(["dt", "validate", "--all"], cwd=work, capture_output=True, text=True)
    assert result.returncode == 3
    assert "HEADING_DUPLICATE" in result.stdout


def test_validate_ignores_headings_inside_fenced_code(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    decisions_dir = work / "decisions"
    decisions_dir.mkdir()
    path = decisions_dir / "DR-0001-fenced.md"
    path.write_text(
        "---\n"
        "id: DR-0001\n"
        "title: Fenced heading example\n"
        "status: proposed\n"
        "type: generic\n"
        "stage: data\n"
        "date: '2026-03-14'\n"
        "owner: ahmet\n"
        "stakeholders: []\n"
        "template_version: '1.0'\n"
        "links: []\n"
        "---\n"
        "\n"
        "## Context\n"
        "The schema can be shown as Markdown:\n\n"
        "```md\n"
        "## Context\n"
        "example\n"
        "```\n\n"
        "## Decision\nx\n\n## Rationale\nx\n\n## Alternatives\nN/A\n\n## Consequences\nx\n",
        encoding="utf-8",
    )

    result = subprocess.run(["dt", "validate", "--all"], cwd=work, capture_output=True, text=True)
    assert result.returncode == 0
    assert "HEADING_DUPLICATE" not in result.stdout
    assert "OK DR-0001" in result.stdout


def test_validate_reports_empty_required_section(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    decisions_dir = work / "decisions"
    decisions_dir.mkdir()
    path = decisions_dir / "DR-0001-empty.md"
    path.write_text(
        "---\n"
        "id: DR-0001\n"
        "title: Empty rationale\n"
        "status: proposed\n"
        "type: generic\n"
        "stage: data\n"
        "date: '2026-03-14'\n"
        "owner: ahmet\n"
        "stakeholders: []\n"
        "template_version: '1.0'\n"
        "links: []\n"
        "---\n"
        "\n"
        "## Context\nx\n\n## Decision\nx\n\n## Rationale\n \n\n## Alternatives\nN/A\n\n## Consequences\nx\n",
        encoding="utf-8",
    )

    result = subprocess.run(["dt", "validate", "--all"], cwd=work, capture_output=True, text=True)
    assert result.returncode == 3
    assert "SECTION_EMPTY" in result.stdout


def test_validate_reports_bad_ref_with_contract_code(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    decisions_dir = work / "decisions"
    decisions_dir.mkdir()
    path = decisions_dir / "DR-0001-bad-ref.md"
    path.write_text(
        "---\n"
        "id: DR-0001\n"
        "title: Bad ref\n"
        "status: accepted\n"
        "type: generic\n"
        "stage: data\n"
        "date: '2026-03-14'\n"
        "owner: ahmet\n"
        "stakeholders: []\n"
        "template_version: '1.0'\n"
        "links:\n"
        "  - id: L-0001\n"
        "    rel: implements\n"
        "    artifact_kind: code\n"
        "    ref: nope\n"
        "---\n"
        "\n"
        "## Context\nx\n\n## Decision\nx\n\n## Rationale\nx\n\n## Alternatives\nN/A\n\n## Consequences\nx\n",
        encoding="utf-8",
    )

    result = subprocess.run(["dt", "validate", "--all"], cwd=work, capture_output=True, text=True)
    assert result.returncode == 3
    assert "LINK_INVALID_FORMAT" in result.stdout


def test_validate_reports_all_errors_for_record(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    decisions_dir = work / "decisions"
    decisions_dir.mkdir()
    path = decisions_dir / "DR-0001-many-errors.md"
    path.write_text(
        "---\n"
        "id: DR-1\n"
        "title: ''\n"
        "status: invalid\n"
        "type: generic\n"
        "stage: data\n"
        "date: '2026-03-14'\n"
        "owner: ''\n"
        "stakeholders: []\n"
        "template_version: '1.0'\n"
        "links: []\n"
        "---\n"
        "\n"
        "## Context\nx\n\n## Decision\nx\n\n## Rationale\nx\n\n## Alternatives\nN/A\n\n## Consequences\nx\n",
        encoding="utf-8",
    )

    result = subprocess.run(["dt", "validate", "--all"], cwd=work, capture_output=True, text=True)
    assert result.returncode == 3
    assert "ID_FORMAT_INVALID" in result.stdout
    assert "ENUM_INVALID" in result.stdout
    assert "owner must be a non-empty string" in result.stdout
    assert "title must be a non-empty string" in result.stdout


def test_validate_warns_on_duplicate_stakeholders(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    decisions_dir = work / "decisions"
    decisions_dir.mkdir()
    path = decisions_dir / "DR-0001-duplicates.md"
    path.write_text(
        "---\n"
        "id: DR-0001\n"
        "title: Duplicate stakeholders\n"
        "status: proposed\n"
        "type: generic\n"
        "stage: data\n"
        "date: '2026-03-14'\n"
        "owner: ahmet\n"
        "stakeholders: [ML engineer, reviewer, ml engineer]\n"
        "template_version: '1.0'\n"
        "links: []\n"
        "---\n"
        "\n"
        "## Context\nx\n\n## Decision\nx\n\n## Rationale\nx\n\n## Alternatives\nN/A\n\n## Consequences\nx\n",
        encoding="utf-8",
    )

    result = subprocess.run(["dt", "validate", "--all"], cwd=work, capture_output=True, text=True)
    assert result.returncode == 0
    assert "WARN DR-0001: STAKEHOLDER_DUPLICATE" in result.stdout
    assert "OK DR-0001" in result.stdout


def test_validate_fails_for_superseded_without_incoming_edge(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    decisions_dir = work / "decisions"
    decisions_dir.mkdir()
    path = decisions_dir / "DR-0001-old.md"
    path.write_text(
        "---\n"
        "id: DR-0001\n"
        "title: Old decision\n"
        "status: superseded\n"
        "type: generic\n"
        "stage: data\n"
        "date: '2026-03-14'\n"
        "owner: ahmet\n"
        "stakeholders: []\n"
        "template_version: '1.0'\n"
        "links:\n"
        "  - id: L-0001\n"
        "    rel: supported_by\n"
        "    artifact_kind: document\n"
        "    ref: path:docs/rule.md\n"
        "---\n"
        "\n"
        "## Context\nx\n\n## Decision\nx\n\n## Rationale\nx\n\n## Alternatives\nN/A\n\n## Consequences\nx\n",
        encoding="utf-8",
    )

    result = subprocess.run(["dt", "validate", "--all"], cwd=work, capture_output=True, text=True)
    assert result.returncode == 3
    assert "SUPERSEDED_INCONSISTENT" in result.stdout


def test_validate_requires_training_config_minima_when_present(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    decisions_dir = work / "decisions"
    decisions_dir.mkdir()
    path = decisions_dir / "DR-0001-model-training.md"
    path.write_text(
        "---\n"
        "id: DR-0001\n"
        "title: Model with incomplete training config\n"
        "status: accepted\n"
        "type: model\n"
        "stage: training\n"
        "date: '2026-03-14'\n"
        "owner: ahmet\n"
        "stakeholders: [reviewer]\n"
        "template_version: '1.0'\n"
        "model_spec:\n"
        "  objective: Text classification\n"
        "  model_family: Transformer encoder\n"
        "  input: Tokenized text\n"
        "  output: Class label\n"
        "  primary_metric: F1\n"
        "  acceptance_criteria: F1 >= 0.75\n"
        "  training_config:\n"
        "    tuning_method: random_search\n"
        "    selected_hyperparameters: {}\n"
        "links:\n"
        "  - id: L-0001\n"
        "    rel: implements\n"
        "    artifact_kind: code\n"
        "    ref: git:commit:abc123\n"
        "  - id: L-0002\n"
        "    rel: supported_by\n"
        "    artifact_kind: document\n"
        "    ref: path:docs/model.md\n"
        "---\n"
        "\n"
        "## Context\nx\n\n## Decision\nx\n\n## Rationale\nx\n\n## Alternatives\nN/A\n\n## Consequences\nx\n",
        encoding="utf-8",
    )

    result = subprocess.run(["dt", "validate", "--all"], cwd=work, capture_output=True, text=True)
    assert result.returncode == 3
    assert "model_spec.training_config.selected_hyperparameters" in result.stdout
    assert "model_spec.training_config.selection_rule" in result.stdout


def test_validate_accepts_complete_training_config_when_present(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    decisions_dir = work / "decisions"
    decisions_dir.mkdir()
    path = decisions_dir / "DR-0001-model-training.md"
    path.write_text(
        "---\n"
        "id: DR-0001\n"
        "title: Model with training config\n"
        "status: accepted\n"
        "type: model\n"
        "stage: training\n"
        "date: '2026-03-14'\n"
        "owner: ahmet\n"
        "stakeholders: [reviewer]\n"
        "template_version: '1.0'\n"
        "model_spec:\n"
        "  objective: Text classification\n"
        "  model_family: Transformer encoder\n"
        "  input: Tokenized text\n"
        "  output: Class label\n"
        "  primary_metric: F1\n"
        "  acceptance_criteria: F1 >= 0.75\n"
        "  training_config:\n"
        "    tuning_method: random_search\n"
        "    selected_hyperparameters:\n"
        "      learning_rate: '3e-5'\n"
        "      batch_size: '16'\n"
        "    selection_rule: Choose highest validation F1\n"
        "links:\n"
        "  - id: L-0001\n"
        "    rel: implements\n"
        "    artifact_kind: code\n"
        "    ref: git:commit:abc123\n"
        "  - id: L-0002\n"
        "    rel: supported_by\n"
        "    artifact_kind: document\n"
        "    ref: path:docs/model.md\n"
        "---\n"
        "\n"
        "## Context\nx\n\n## Decision\nx\n\n## Rationale\nx\n\n## Alternatives\nN/A\n\n## Consequences\nx\n",
        encoding="utf-8",
    )

    result = subprocess.run(["dt", "validate", "--all"], cwd=work, capture_output=True, text=True)
    assert result.returncode == 0
    assert "OK DR-0001" in result.stdout


def test_validate_warns_for_missing_git_commit_inside_git_repo(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    _run_git_or_skip(["--version"], work)
    _run_git_or_skip(["init"], work)
    decisions_dir = work / "decisions"
    decisions_dir.mkdir()
    path = decisions_dir / "DR-0001-git-link.md"
    path.write_text(
        "---\n"
        "id: DR-0001\n"
        "title: Git linked decision\n"
        "status: accepted\n"
        "type: generic\n"
        "stage: training\n"
        "date: '2026-03-14'\n"
        "owner: ahmet\n"
        "stakeholders: [reviewer]\n"
        "template_version: '1.0'\n"
        "links:\n"
        "  - id: L-0001\n"
        "    rel: implements\n"
        "    artifact_kind: code\n"
        "    ref: git:commit:deadbeef\n"
        "---\n"
        "\n"
        "## Context\nx\n\n## Decision\nx\n\n## Rationale\nx\n\n## Alternatives\nN/A\n\n## Consequences\nx\n",
        encoding="utf-8",
    )

    result = subprocess.run(["dt", "validate", "--all"], cwd=work, capture_output=True, text=True)
    assert result.returncode == 0
    assert "WARN DR-0001: GIT_COMMIT_NOT_FOUND" in result.stdout
    assert "OK DR-0001" in result.stdout


def test_validate_skips_git_commit_check_outside_git_repo(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    decisions_dir = work / "decisions"
    decisions_dir.mkdir()
    path = decisions_dir / "DR-0001-git-link.md"
    path.write_text(
        "---\n"
        "id: DR-0001\n"
        "title: Git linked decision\n"
        "status: accepted\n"
        "type: generic\n"
        "stage: training\n"
        "date: '2026-03-14'\n"
        "owner: ahmet\n"
        "stakeholders: [reviewer]\n"
        "template_version: '1.0'\n"
        "links:\n"
        "  - id: L-0001\n"
        "    rel: implements\n"
        "    artifact_kind: code\n"
        "    ref: git:commit:deadbeef\n"
        "---\n"
        "\n"
        "## Context\nx\n\n## Decision\nx\n\n## Rationale\nx\n\n## Alternatives\nN/A\n\n## Consequences\nx\n",
        encoding="utf-8",
    )

    result = subprocess.run(["dt", "validate", "--all"], cwd=work, capture_output=True, text=True)
    assert result.returncode == 0
    assert "GIT_COMMIT_NOT_FOUND" not in result.stdout
    assert "OK DR-0001" in result.stdout


def test_validate_warns_when_git_commit_check_is_unavailable(monkeypatch, tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    decisions_dir = work / "decisions"
    decisions_dir.mkdir()
    path = decisions_dir / "DR-0001-git-link.md"
    path.write_text(
        "---\n"
        "id: DR-0001\n"
        "title: Git linked decision\n"
        "status: accepted\n"
        "type: generic\n"
        "stage: training\n"
        "date: '2026-03-14'\n"
        "owner: ahmet\n"
        "stakeholders: [reviewer]\n"
        "template_version: '1.0'\n"
        "links:\n"
        "  - id: L-0001\n"
        "    rel: implements\n"
        "    artifact_kind: code\n"
        "    ref: git:commit:deadbeef\n"
        "---\n"
        "\n"
        "## Context\nx\n\n## Decision\nx\n\n## Rationale\nx\n\n## Alternatives\nN/A\n\n## Consequences\nx\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("dt.commands._git_repo_root", lambda _root: work)
    monkeypatch.setattr(
        "dt.validation._git_commit_check",
        lambda _root, _sha: GitCommitCheck("unavailable", "git executable was not found"),
    )
    runner = CliRunner()

    result = runner.invoke(app, ["validate", "--all", "--root", str(work)])
    strict = runner.invoke(app, ["validate", "--all", "--strict", "--root", str(work)])

    assert result.exit_code == 0
    assert "WARN DR-0001: GIT_COMMIT_CHECK_UNAVAILABLE" in result.output
    assert "git executable was not found" in result.output
    assert "GIT_COMMIT_NOT_FOUND" not in result.output
    assert strict.exit_code == 3


def test_validate_missing_decisions_dir_is_filesystem_error(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()

    result = subprocess.run(["dt", "validate", "--all"], cwd=work, capture_output=True, text=True)
    assert result.returncode == 2
    assert "FAIL DECISIONS_DIR_MISSING" in result.stdout
