import json
import shutil
import subprocess
import sys
from pathlib import Path


def _prepare_site_workdir(tmp_path: Path) -> Path:
    repo = Path(__file__).resolve().parents[1]
    work = tmp_path / "work"
    work.mkdir()
    shutil.copytree(repo / "src", work / "src")
    shutil.copytree(repo / "viewer", work / "viewer")
    decisions_dir = work / "decisions"
    decisions_dir.mkdir()
    for path in (repo / "fixtures" / "decisions").glob("*.md"):
        shutil.copy2(path, decisions_dir / path.name)
    return work


def test_build_site_creates_clean_static_artifact(tmp_path: Path):
    repo = Path(__file__).resolve().parents[1]
    work = _prepare_site_workdir(tmp_path)

    result = subprocess.run(
        [sys.executable, str(repo / "scripts" / "build_site.py"), "--root", str(work)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    site = work / "_site"
    data = site / "data"
    for path in [
        site / "index.html",
        site / "report.html",
        site / "app.js",
        site / "styles.css",
        data / "index.json",
        data / "graph.json",
        data / "artifacts.json",
        data / "report.md",
        data / "metrics.csv",
        data / "validation.txt",
        data / "site-meta.json",
    ]:
        assert path.exists(), f"Missing site artifact: {path}"

    assert not (site / "decisions").exists()
    assert 'dataBase: "data"' in (site / "index.html").read_text(encoding="utf-8")
    assert 'reportPath: "report.html"' in (site / "index.html").read_text(encoding="utf-8")
    report_html = (site / "report.html").read_text(encoding="utf-8")
    assert "Decision Tracker Audit Report" in report_html
    assert "Executive Summary" in report_html
    assert "Print report" in report_html
    assert "data/metrics.csv" in report_html
    assert "OK DR-0001" in (data / "validation.txt").read_text(encoding="utf-8")

    meta = json.loads((data / "site-meta.json").read_text(encoding="utf-8"))
    assert sorted(meta) == ["generated_from_commit", "source_branch"]


def test_build_site_stops_on_validation_failure(tmp_path: Path):
    repo = Path(__file__).resolve().parents[1]
    work = _prepare_site_workdir(tmp_path)
    target = next((work / "decisions").glob("DR-0001-*.md"))
    text = target.read_text(encoding="utf-8")
    target.write_text(text.replace("stage: monitoring", "stage: invalid"), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(repo / "scripts" / "build_site.py"), "--root", str(work)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 3
    assert "FAIL DR-0001: ENUM_INVALID" in result.stderr
    assert not (work / "_site").exists()


def test_build_site_requires_viewer_config_placeholder(tmp_path: Path):
    repo = Path(__file__).resolve().parents[1]
    work = _prepare_site_workdir(tmp_path)
    index_path = work / "viewer" / "index.html"
    index_path.write_text(
        index_path.read_text(encoding="utf-8").replace(
            "<script>\n      window.DT_VIEWER_CONFIG = window.DT_VIEWER_CONFIG || {};\n    </script>",
            "",
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(repo / "scripts" / "build_site.py"), "--root", str(work)],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "DT_VIEWER_CONFIG placeholder" in result.stderr
