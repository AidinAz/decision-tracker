from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def _run_git_or_skip(args: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=env)
    except FileNotFoundError:
        pytest.skip("git is not available")
    if result.returncode != 0 and args[:1] == ["--version"]:
        pytest.skip("git is not available")
    assert result.returncode == 0, result.stderr
    return result


def _commit_file(repo: Path, filename: str, content: str, message: str, timestamp: str) -> str:
    path = repo / filename
    path.write_text(content, encoding="utf-8")
    _run_git_or_skip(["add", filename], repo)
    env = os.environ.copy()
    env["GIT_AUTHOR_DATE"] = timestamp
    env["GIT_COMMITTER_DATE"] = timestamp
    _run_git_or_skip(["commit", "-m", message], repo, env=env)
    return _run_git_or_skip(["rev-parse", "--verify", "HEAD"], repo).stdout.strip()


def _read_front_matter(path: Path) -> dict:
    content = path.read_text(encoding="utf-8")
    yaml_text = content.split("\n---\n", 1)[0][4:]
    parsed = yaml.safe_load(yaml_text)
    assert isinstance(parsed, dict)
    return parsed


def test_discover_fails_clearly_outside_git_repo(tmp_path: Path):
    result = _run(["dt", "discover", "--root", str(tmp_path)], tmp_path)

    assert result.returncode == 2
    assert "FAIL DISCOVER_GIT_FAILED" in result.stdout
    assert list(tmp_path.iterdir()) == []


def test_discover_prints_no_candidates_when_git_scan_succeeds(tmp_path: Path):
    work = tmp_path / "repo"
    work.mkdir()
    _run_git_or_skip(["--version"], work)
    _run_git_or_skip(["init"], work)
    _run_git_or_skip(["config", "user.email", "test@example.com"], work)
    _run_git_or_skip(["config", "user.name", "Test User"], work)
    _commit_file(work, "notes.txt", "notes\n", "Update readme text", "2026-01-01T00:00:00+0000")

    result = _run(["dt", "discover", "--root", str(work), "--keywords", "hyperparameter"], work)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "No candidate decision evidence found." in result.stdout


def test_discover_keywords_match_words_not_substrings(tmp_path: Path):
    work = tmp_path / "repo"
    work.mkdir()
    _run_git_or_skip(["--version"], work)
    _run_git_or_skip(["init"], work)
    _run_git_or_skip(["config", "user.email", "test@example.com"], work)
    _run_git_or_skip(["config", "user.name", "Test User"], work)
    _commit_file(work, "notes.txt", "notes\n", "Pinpoint flaky test", "2026-01-01T00:00:00+0000")

    result = _run(["dt", "discover", "--root", str(work), "--keywords", "pin"], work)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "No candidate decision evidence found." in result.stdout


def test_discover_finds_git_commit_candidates_and_respects_limit_since_keywords(tmp_path: Path):
    work = tmp_path / "repo"
    work.mkdir()
    _run_git_or_skip(["--version"], work)
    _run_git_or_skip(["init"], work)
    _run_git_or_skip(["config", "user.email", "test@example.com"], work)
    _run_git_or_skip(["config", "user.name", "Test User"], work)

    _commit_file(work, "old.txt", "old\n", "Switch baseline model", "2023-01-01T00:00:00+0000")
    _commit_file(work, "new.txt", "new\n", "Pin dataset version", "2026-01-01T00:00:00+0000")
    kept_sha = _commit_file(work, "other.txt", "other\n", "Adjust metric threshold", "2026-01-02T00:00:00+0000")

    result = _run(
        [
            "dt",
            "discover",
            "--root",
            str(work),
            "--since",
            "2025-01-01",
            "--limit",
            "1",
            "--keywords",
            "pin,threshold",
        ],
        work,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Found 1 candidate decision evidence item(s)." in result.stdout
    assert "Adjust metric threshold" in result.stdout
    assert f"git:commit:{kept_sha}" in result.stdout
    assert "suggested stage: evaluation" in result.stdout
    assert "suggested type: evaluation_protocol" in result.stdout
    assert "Pin dataset version" not in result.stdout


def test_discover_reports_invalid_since_as_git_failure(tmp_path: Path):
    work = tmp_path / "repo"
    work.mkdir()
    _run_git_or_skip(["--version"], work)
    _run_git_or_skip(["init"], work)
    _run_git_or_skip(["config", "user.email", "test@example.com"], work)
    _run_git_or_skip(["config", "user.name", "Test User"], work)
    _commit_file(work, "notes.txt", "notes\n", "Pin dataset version", "2026-01-01T00:00:00+0000")

    result = _run(["dt", "discover", "--root", str(work), "--since", "garbage date"], work)

    assert result.returncode == 2
    assert "FAIL DISCOVER_GIT_FAILED" in result.stdout


def test_backfill_requires_initialized_decisions_dir(tmp_path: Path):
    result = _run(
        [
            "dt",
            "backfill",
            "--root",
            str(tmp_path),
            "--title",
            "Past decision",
            "--stage",
            "training",
            "--type",
            "generic",
            "--owner",
            "ahmet",
            "--evidence",
            "git:commit:abc1234",
        ],
        tmp_path,
    )

    assert result.returncode == 2
    assert "FAIL DECISIONS_DIR_MISSING" in result.stdout


def test_backfill_rejects_invalid_evidence_refs(tmp_path: Path):
    decisions = tmp_path / "decisions"
    decisions.mkdir()

    result = _run(
        [
            "dt",
            "backfill",
            "--root",
            str(tmp_path),
            "--title",
            "Past decision",
            "--stage",
            "training",
            "--type",
            "generic",
            "--owner",
            "ahmet",
            "--original-decision-date",
            "unknown",
            "--evidence",
            "not-a-ref",
            "--confidence",
            "medium",
        ],
        tmp_path,
    )

    assert result.returncode == 2
    assert "FAIL BACKFILL_INVALID_EVIDENCE" in result.stdout
    assert not list(decisions.glob("DR-*.md"))


def test_backfill_rejects_symbolic_and_too_short_git_commit_evidence(tmp_path: Path):
    decisions = tmp_path / "decisions"
    decisions.mkdir()

    for ref in ("git:commit:HEAD", "git:commit:abc"):
        result = _run(
            [
                "dt",
                "backfill",
                "--root",
                str(tmp_path),
                "--title",
                "Past decision",
                "--stage",
                "training",
                "--type",
                "generic",
                "--owner",
                "ahmet",
                "--original-decision-date",
                "unknown",
                "--evidence",
                ref,
                "--confidence",
                "medium",
            ],
            tmp_path,
        )

        assert result.returncode == 2
        assert "git commit evidence must be git:commit:<7-40 hex chars>" in result.stdout
    assert not list(decisions.glob("DR-*.md"))


def test_backfill_accepts_url_evidence(tmp_path: Path):
    decisions = tmp_path / "decisions"
    decisions.mkdir()

    result = _run(
        [
            "dt",
            "backfill",
            "--root",
            str(tmp_path),
            "--title",
            "URL evidence",
            "--stage",
            "training",
            "--type",
            "generic",
            "--owner",
            "ahmet",
            "--original-decision-date",
            "unknown",
            "--evidence",
            "url:https://example.com/notes",
            "--confidence",
            "high",
            "--context",
            "Context",
            "--decision",
            "Decision",
            "--rationale",
            "Rationale",
            "--alternatives",
            "Alternative",
            "--consequences",
            "Consequence",
        ],
        tmp_path,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    front = _read_front_matter(decisions / "DR-0001-url-evidence.md")
    assert front["links"][0]["ref"] == "url:https://example.com/notes"
    assert front["links"][0]["rel"] == "supported_by"
    assert front["links"][0]["artifact_kind"] == "document"


def test_backfill_unsupported_evidence_lists_supported_prefixes(tmp_path: Path):
    decisions = tmp_path / "decisions"
    decisions.mkdir()

    result = _run(
        [
            "dt",
            "backfill",
            "--root",
            str(tmp_path),
            "--title",
            "Unsupported evidence",
            "--stage",
            "training",
            "--type",
            "generic",
            "--owner",
            "ahmet",
            "--original-decision-date",
            "unknown",
            "--evidence",
            "git:ref:main",
            "--confidence",
            "medium",
        ],
        tmp_path,
    )

    assert result.returncode == 2
    assert "Supported prefixes" in result.stdout
    assert "url:https://" in result.stdout


def test_backfill_creates_valid_proposed_record_with_reconstruction(tmp_path: Path):
    decisions = tmp_path / "decisions"
    decisions.mkdir()

    result = _run(
        [
            "dt",
            "backfill",
            "--root",
            str(tmp_path),
            "--title",
            "Reconstruct baseline choice",
            "--stage",
            "training",
            "--type",
            "model",
            "--owner",
            "ahmet",
            "--stakeholders",
            "ML engineer, reviewer",
            "--original-decision-date",
            "2025-03-10",
            "--evidence",
            "git:commit:abc1234,path:docs/model-notes.md,run:offline-eval-1",
            "--confidence",
            "medium",
            "--known-gaps",
            "Original meeting notes unavailable;Alternatives reconstructed later",
            "--context",
            "Existing baseline had limited traceability.",
            "--decision",
            "Use the transformer baseline.",
            "--rationale",
            "Historical evidence points to better validation F1.",
            "--alternatives",
            "BiLSTM baseline.",
            "--consequences",
            "Training became more expensive.",
        ],
        tmp_path,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Review this proposed backfill record" in result.stdout

    created = decisions / "DR-0001-reconstruct-baseline-choice.md"
    assert created.exists()
    front = _read_front_matter(created)
    assert front["status"] == "proposed"
    assert front["type"] == "model"
    assert front["stakeholders"] == ["ML engineer", "reviewer"]
    assert front["reconstruction"] == {
        "mode": "backfill",
        "original_decision_date": "2025-03-10",
        "evidence_confidence": "medium",
        "evidence_sources": ["git:commit:abc1234", "path:docs/model-notes.md", "run:offline-eval-1"],
        "known_gaps": ["Original meeting notes unavailable", "Alternatives reconstructed later"],
    }
    assert front["links"][:3] == [
        {
            "id": "L-0001",
            "rel": "implements",
            "artifact_kind": "code",
            "ref": "git:commit:abc1234",
            "label": "Backfill evidence 1",
            "note": "Historical reconstruction evidence",
        },
        {
            "id": "L-0002",
            "rel": "supported_by",
            "artifact_kind": "document",
            "ref": "path:docs/model-notes.md",
            "label": "Backfill evidence 2",
            "note": "Historical reconstruction evidence",
        },
        {
            "id": "L-0003",
            "rel": "evaluated_by",
            "artifact_kind": "experiment_run",
            "ref": "run:offline-eval-1",
            "label": "Backfill evidence 3",
            "note": "Historical reconstruction evidence",
        },
    ]
    assert "model_spec" in front

    validate = _run(["dt", "validate", "--all"], tmp_path)
    assert validate.returncode == 0, validate.stdout + validate.stderr
    assert "OK DR-0001" in validate.stdout

    report = _run(["dt", "report"], tmp_path)
    assert report.returncode == 0, report.stdout + report.stderr
    index = json.loads((decisions / "index.json").read_text(encoding="utf-8"))
    assert index[0]["reconstruction"]["mode"] == "backfill"
    assert index[0]["reconstruction"]["evidence_sources"] == [
        "git:commit:abc1234",
        "path:docs/model-notes.md",
        "run:offline-eval-1",
    ]


def test_validate_rejects_invalid_reconstruction_metadata(tmp_path: Path):
    decisions = tmp_path / "decisions"
    decisions.mkdir()
    (decisions / "DR-0001-bad-reconstruction.md").write_text(
        "---\n"
        "id: DR-0001\n"
        "title: Bad reconstruction\n"
        "status: proposed\n"
        "type: generic\n"
        "stage: training\n"
        "date: '2026-03-14'\n"
        "owner: ahmet\n"
        "stakeholders: []\n"
        "template_version: '1.0'\n"
        "links: []\n"
        "reconstruction:\n"
        "  mode: automatic\n"
        "  original_decision_date: '2026-02-30'\n"
        "  evidence_confidence: certain\n"
        "  evidence_sources: []\n"
        "  known_gaps: missing\n"
        "---\n"
        "\n"
        "## Context\nx\n\n## Decision\nx\n\n## Rationale\nx\n\n## Alternatives\nN/A\n\n## Consequences\nx\n",
        encoding="utf-8",
    )

    result = _run(["dt", "validate", "--all"], tmp_path)

    assert result.returncode == 3
    assert "RECONSTRUCTION_INVALID" in result.stdout
