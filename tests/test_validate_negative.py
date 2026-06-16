import shutil
import subprocess
from pathlib import Path

import pytest


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


def test_validate_missing_decisions_dir_is_filesystem_error(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()

    result = subprocess.run(["dt", "validate", "--all"], cwd=work, capture_output=True, text=True)
    assert result.returncode == 2
