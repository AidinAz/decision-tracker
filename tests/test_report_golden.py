import shutil
import subprocess
from pathlib import Path


def run(cmd: list[str], cwd: Path):
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    assert result.returncode == 0, f"Command failed: {cmd}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    return result


def test_report_matches_golden(tmp_path: Path):
    repo = Path(__file__).resolve().parents[1]
    fixtures_decisions = repo / "fixtures" / "decisions"
    fixtures_expected = repo / "fixtures" / "expected"

    work = tmp_path / "work"
    work.mkdir()
    decisions_dir = work / "decisions"
    reports_dir = work / "reports"
    decisions_dir.mkdir()
    reports_dir.mkdir()
    for path in fixtures_decisions.glob("*.md"):
        shutil.copy2(path, decisions_dir / path.name)

    run(["dt", "report"], cwd=work)

    pairs = [
        (fixtures_expected / "index.json", decisions_dir / "index.json"),
        (fixtures_expected / "graph.json", decisions_dir / "graph.json"),
        (fixtures_expected / "artifacts.json", decisions_dir / "artifacts.json"),
        (fixtures_expected / "metrics.csv", reports_dir / "metrics.csv"),
        (fixtures_expected / "report.md", reports_dir / "report.md"),
    ]
    for expected, actual in pairs:
        assert actual.exists(), f"Missing output: {actual}"
        assert expected.read_bytes() == actual.read_bytes(), f"Mismatch in {actual.name}"
    report_text = (reports_dir / "report.md").read_text(encoding="utf-8")
    assert "## Executive summary" in report_text
    assert "## Attention items" in report_text
    assert "## Reconstructed records" in report_text


def test_report_is_deterministic_across_runs(tmp_path: Path):
    repo = Path(__file__).resolve().parents[1]
    fixtures_decisions = repo / "fixtures" / "decisions"

    work = tmp_path / "work"
    work.mkdir()
    decisions_dir = work / "decisions"
    reports_dir = work / "reports"
    decisions_dir.mkdir()
    reports_dir.mkdir()
    for path in fixtures_decisions.glob("*.md"):
        shutil.copy2(path, decisions_dir / path.name)

    run(["dt", "report"], cwd=work)
    first = {
        "index": (decisions_dir / "index.json").read_bytes(),
        "graph": (decisions_dir / "graph.json").read_bytes(),
        "artifacts": (decisions_dir / "artifacts.json").read_bytes(),
        "metrics": (reports_dir / "metrics.csv").read_bytes(),
        "report": (reports_dir / "report.md").read_bytes(),
    }

    run(["dt", "report"], cwd=work)
    second = {
        "index": (decisions_dir / "index.json").read_bytes(),
        "graph": (decisions_dir / "graph.json").read_bytes(),
        "artifacts": (decisions_dir / "artifacts.json").read_bytes(),
        "metrics": (reports_dir / "metrics.csv").read_bytes(),
        "report": (reports_dir / "report.md").read_bytes(),
    }

    assert first == second


def test_report_preserves_user_json_while_rewriting_generated_outputs(tmp_path: Path):
    repo = Path(__file__).resolve().parents[1]
    fixtures_decisions = repo / "fixtures" / "decisions"

    work = tmp_path / "work"
    work.mkdir()
    decisions_dir = work / "decisions"
    reports_dir = work / "reports"
    decisions_dir.mkdir()
    reports_dir.mkdir()
    for path in fixtures_decisions.glob("*.md"):
        shutil.copy2(path, decisions_dir / path.name)
    user_json = decisions_dir / "extra.json"
    user_json.write_text('{"team": "notes"}\n', encoding="utf-8")
    generated_index = decisions_dir / "index.json"
    generated_index.write_text('{"stale": true}\n', encoding="utf-8")

    run(["dt", "report"], cwd=work)

    assert user_json.read_text(encoding="utf-8") == '{"team": "notes"}\n'
    assert generated_index.read_text(encoding="utf-8") != '{"stale": true}\n'
    assert (decisions_dir / "index.json").exists()
    assert (decisions_dir / "graph.json").exists()
    assert (decisions_dir / "artifacts.json").exists()


def test_report_missing_decisions_dir_is_filesystem_error(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()

    result = subprocess.run(["dt", "report"], cwd=work, capture_output=True, text=True)
    assert result.returncode == 2
    assert "FAIL DECISIONS_DIR_MISSING" in result.stdout


def test_report_discovers_root_from_subdirectory(tmp_path: Path):
    repo = Path(__file__).resolve().parents[1]
    fixtures_decisions = repo / "fixtures" / "decisions"

    work = tmp_path / "work"
    work.mkdir()
    decisions_dir = work / "decisions"
    subdir = work / "nested" / "deeper"
    decisions_dir.mkdir()
    subdir.mkdir(parents=True)
    for path in fixtures_decisions.glob("*.md"):
        shutil.copy2(path, decisions_dir / path.name)

    run(["dt", "report"], cwd=subdir)

    assert (work / "decisions" / "index.json").exists()
    assert (work / "reports" / "metrics.csv").exists()
    assert not (subdir / "reports" / "metrics.csv").exists()


def test_report_discovery_prefers_decisions_over_nested_git(tmp_path: Path):
    repo = Path(__file__).resolve().parents[1]
    fixtures_decisions = repo / "fixtures" / "decisions"

    work = tmp_path / "work"
    work.mkdir()
    decisions_dir = work / "decisions"
    nested = work / "nested"
    subdir = nested / "deeper"
    decisions_dir.mkdir()
    (nested / ".git").mkdir(parents=True)
    subdir.mkdir()
    for path in fixtures_decisions.glob("*.md"):
        shutil.copy2(path, decisions_dir / path.name)

    run(["dt", "report"], cwd=subdir)

    assert (work / "decisions" / "index.json").exists()
    assert (work / "reports" / "metrics.csv").exists()
    assert not (nested / "reports" / "metrics.csv").exists()


def test_report_discovery_falls_back_to_git_root_without_decisions(tmp_path: Path):
    work = tmp_path / "work"
    subdir = work / "nested" / "deeper"
    (work / ".git").mkdir(parents=True)
    subdir.mkdir(parents=True)

    result = subprocess.run(["dt", "report"], cwd=subdir, capture_output=True, text=True)

    assert result.returncode == 2
    assert f"FAIL DECISIONS_DIR_MISSING: No decisions/ directory found at {work}" in result.stdout


def test_report_uses_explicit_root(tmp_path: Path):
    repo = Path(__file__).resolve().parents[1]
    fixtures_decisions = repo / "fixtures" / "decisions"

    work = tmp_path / "work"
    other = tmp_path / "other"
    work.mkdir()
    other.mkdir()
    decisions_dir = work / "decisions"
    decisions_dir.mkdir()
    for path in fixtures_decisions.glob("*.md"):
        shutil.copy2(path, decisions_dir / path.name)

    run(["dt", "report", "--root", str(work)], cwd=other)

    assert (work / "decisions" / "index.json").exists()
    assert (work / "reports" / "metrics.csv").exists()
    assert not (other / "reports" / "metrics.csv").exists()


def test_report_fails_before_generating_on_validation_errors(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    decisions_dir = work / "decisions"
    decisions_dir.mkdir()
    (decisions_dir / "DR-0001-invalid.md").write_text(
        "---\n"
        "id: DR-0001\n"
        "title: Invalid decision\n"
        "status: accepted\n"
        "type: generic\n"
        "stage: invalid\n"
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

    result = subprocess.run(["dt", "report"], cwd=work, capture_output=True, text=True)
    assert result.returncode == 3
    assert "FAIL DR-0001: ENUM_INVALID" in result.stdout
    assert not (decisions_dir / "index.json").exists()
