from pathlib import Path

from typer.testing import CliRunner

from dt.cli import app


def test_init_creates_minimal_scaffold(tmp_path: Path):
    runner = CliRunner()

    result = runner.invoke(app, ["init", "--root", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert (tmp_path / "decisions" / ".gitkeep").exists()
    gitignore = tmp_path / ".gitignore"
    assert gitignore.exists()
    assert "_site/" in gitignore.read_text(encoding="utf-8")
    assert "decisions/index.json" in gitignore.read_text(encoding="utf-8")
    assert (tmp_path / "docs" / "README.md").exists()
    workflow = tmp_path / ".github" / "workflows" / "pages.yml"
    assert workflow.exists()
    text = workflow.read_text(encoding="utf-8")
    assert "dt validate --all" in text
    assert "dt report" in text
    assert "dt build-site --root ." in text
    assert "git+https://github.com/AhmetIsk/decision-tracker.git@v0.1.0" in text
    assert "After the package is published to PyPI" in text


def test_init_does_not_overwrite_existing_files_without_force(tmp_path: Path):
    runner = CliRunner()
    workflow = tmp_path / ".github" / "workflows" / "pages.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("custom workflow\n", encoding="utf-8")

    result = runner.invoke(app, ["init", "--root", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert workflow.read_text(encoding="utf-8") == "custom workflow\n"
    assert "Exists" in result.output


def test_init_appends_gitignore_block_idempotently(tmp_path: Path):
    runner = CliRunner()
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("*.log\n", encoding="utf-8")

    result = runner.invoke(app, ["init", "--root", str(tmp_path)])
    second = runner.invoke(app, ["init", "--root", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert second.exit_code == 0, second.output
    text = gitignore.read_text(encoding="utf-8")
    assert "*.log" in text
    assert "# >>> Decision Tracker generated outputs >>>" in text
    assert "_site/" in text
    assert text.count("# >>> Decision Tracker generated outputs >>>") == 1
    assert "Updated .gitignore" in result.output
    assert "Updated .gitignore" not in second.output


def test_init_repairs_partial_gitignore_marker_block(tmp_path: Path):
    runner = CliRunner()
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("*.log\n# >>> Decision Tracker generated outputs >>>\nbroken\n", encoding="utf-8")

    result = runner.invoke(app, ["init", "--root", str(tmp_path)])

    assert result.exit_code == 0, result.output
    text = gitignore.read_text(encoding="utf-8")
    assert "*.log" in text
    assert "broken" not in text
    assert text.count("# >>> Decision Tracker generated outputs >>>") == 1
    assert text.count("# <<< Decision Tracker generated outputs <<<") == 1
    assert "_site/" in text
    assert "Updated .gitignore" in result.output


def test_init_force_overwrites_scaffolded_files(tmp_path: Path):
    runner = CliRunner()
    workflow = tmp_path / ".github" / "workflows" / "pages.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("custom workflow\n", encoding="utf-8")

    result = runner.invoke(app, ["init", "--root", str(tmp_path), "--force"])

    assert result.exit_code == 0, result.output
    assert "dt build-site --root ." in workflow.read_text(encoding="utf-8")
    assert "Replaced" in result.output


def test_init_force_does_not_report_identical_files_as_replaced(tmp_path: Path):
    runner = CliRunner()

    first = runner.invoke(app, ["init", "--root", str(tmp_path)])
    second = runner.invoke(app, ["init", "--root", str(tmp_path), "--force"])

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    assert "Replaced" not in second.output
    assert "Unchanged" in second.output
