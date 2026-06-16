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


def test_report_missing_decisions_dir_is_filesystem_error(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()

    result = subprocess.run(["dt", "report"], cwd=work, capture_output=True, text=True)
    assert result.returncode == 2


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
