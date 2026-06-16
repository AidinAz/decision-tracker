import subprocess
import unittest
from contextlib import contextmanager
from pathlib import Path

import yaml
from typer.testing import CliRunner

from dt.cli import app


@contextmanager
def _pushd(path: Path):
    original = Path.cwd()
    try:
        import os

        os.chdir(path)
        yield
    finally:
        os.chdir(original)


class TestDtNew(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()

    def _read_front_matter(self, path: Path) -> dict:
        content = path.read_text(encoding="utf-8")
        self.assertTrue(content.startswith("---\n"))
        parts = content.split("\n---\n", 1)
        self.assertEqual(len(parts), 2)
        return yaml.safe_load(parts[0][4:])

    def _created_path(self, output: str) -> Path:
        prefix = "Created "
        self.assertTrue(output.startswith(prefix), msg=output)
        return Path(output[len(prefix) :].strip())

    def _run_git(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            result = subprocess.run(["git", *args], capture_output=True, text=True)
        except FileNotFoundError:
            self.skipTest("git is not available")
        if result.returncode != 0 and args[:1] == ["--version"]:
            self.skipTest("git is not available")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        return result

    def test_new_allocates_next_id_from_existing_records(self) -> None:
        with self.runner.isolated_filesystem():
            decisions_dir = Path("decisions")
            decisions_dir.mkdir()
            decisions_dir.joinpath("DR-0001-first.md").write_text(
                "---\n"
                "id: DR-0001\n"
                "title: first\n"
                "status: proposed\n"
                "type: generic\n"
                "stage: data\n"
                "date: '2026-01-01'\n"
                "owner: ahmet\n"
                "stakeholders: []\n"
                "template_version: '1.0'\n"
                "links: []\n"
                "---\n"
                "\n"
                "## Context\nx\n\n## Decision\nx\n\n## Rationale\nx\n\n## Alternatives\nN/A\n\n## Consequences\nx\n",
                encoding="utf-8",
            )
            decisions_dir.joinpath("DR-0009-last.md").write_text(
                "---\n"
                "id: DR-0009\n"
                "title: last\n"
                "status: proposed\n"
                "type: generic\n"
                "stage: data\n"
                "date: '2026-01-01'\n"
                "owner: ahmet\n"
                "stakeholders: []\n"
                "template_version: '1.0'\n"
                "links: []\n"
                "---\n"
                "\n"
                "## Context\nx\n\n## Decision\nx\n\n## Rationale\nx\n\n## Alternatives\nN/A\n\n## Consequences\nx\n",
                encoding="utf-8",
            )

            result = self.runner.invoke(
                app,
                [
                    "new",
                    "--title",
                    "My New Decision",
                    "--stage",
                    "evaluation",
                    "--type",
                    "generic",
                    "--owner",
                    "ahmet",
                ],
            )
            self.assertEqual(result.exit_code, 0, msg=result.output)
            created = self._created_path(result.output)
            self.assertTrue(created.exists())
            self.assertEqual(created.name, "DR-0010-my-new-decision.md")

    def test_new_creates_required_content_and_stakeholders_dedup(self) -> None:
        with self.runner.isolated_filesystem():
            result = self.runner.invoke(
                app,
                [
                    "new",
                    "--title",
                    "Threshold Tuning",
                    "--stage",
                    "evaluation",
                    "--type",
                    "evaluation_protocol",
                    "--owner",
                    "ahmet",
                    "--stakeholders",
                    "ML Engineer, reviewer, ml engineer, Reviewer,  ",
                ],
            )
            self.assertEqual(result.exit_code, 0, msg=result.output)
            created = self._created_path(result.output)
            self.assertEqual(created.name, "DR-0001-threshold-tuning.md")
            self.assertTrue(created.exists())

            front = self._read_front_matter(created)
            self.assertEqual(front["id"], "DR-0001")
            self.assertEqual(front["status"], "proposed")
            self.assertEqual(front["template_version"], "1.0")
            self.assertEqual(front["links"], [])
            self.assertEqual(front["stakeholders"], ["ML Engineer", "reviewer"])

            content = created.read_text(encoding="utf-8")
            for heading in [
                "## Context",
                "## Decision",
                "## Rationale",
                "## Alternatives",
                "## Consequences",
            ]:
                self.assertIn(heading, content)

            self.assertFalse(Path("decisions/index.json").exists())
            self.assertFalse(Path("decisions/graph.json").exists())
            self.assertFalse(Path("decisions/artifacts.json").exists())
            self.assertFalse(Path("reports/metrics.csv").exists())
            self.assertFalse(Path("reports/report.md").exists())

    def test_new_discovers_root_from_subdirectory(self) -> None:
        with self.runner.isolated_filesystem():
            decisions_dir = Path("decisions")
            nested = Path("nested") / "deeper"
            decisions_dir.mkdir()
            nested.mkdir(parents=True)

            with _pushd(nested):
                result = self.runner.invoke(
                    app,
                    [
                        "new",
                        "--title",
                        "Subdir Decision",
                        "--stage",
                        "data",
                        "--type",
                        "generic",
                        "--owner",
                        "ahmet",
                    ],
                )

            self.assertEqual(result.exit_code, 0, msg=result.output)
            created = self._created_path(result.output)
            self.assertEqual(created.as_posix(), "decisions/DR-0001-subdir-decision.md")
            self.assertTrue((decisions_dir / "DR-0001-subdir-decision.md").exists())
            self.assertFalse((nested / "decisions").exists())

    def test_new_adds_model_template_fields(self) -> None:
        with self.runner.isolated_filesystem():
            result = self.runner.invoke(
                app,
                [
                    "new",
                    "--title",
                    "Model Baseline",
                    "--stage",
                    "training",
                    "--type",
                    "model",
                    "--owner",
                    "ahmet",
                ],
            )
            self.assertEqual(result.exit_code, 0, msg=result.output)
            created = self._created_path(result.output)
            front = self._read_front_matter(created)

            self.assertIn("model_spec", front)
            self.assertEqual(
                sorted(front["model_spec"].keys()),
                sorted(
                    [
                        "objective",
                        "model_family",
                        "input",
                        "output",
                        "primary_metric",
                        "acceptance_criteria",
                    ]
                ),
            )

    def test_new_adds_evaluation_protocol_template_fields(self) -> None:
        with self.runner.isolated_filesystem():
            result = self.runner.invoke(
                app,
                [
                    "new",
                    "--title",
                    "Evaluation Protocol",
                    "--stage",
                    "evaluation",
                    "--type",
                    "evaluation_protocol",
                    "--owner",
                    "ahmet",
                ],
            )
            self.assertEqual(result.exit_code, 0, msg=result.output)
            created = self._created_path(result.output)
            front = self._read_front_matter(created)

            self.assertIn("eval_spec", front)
            self.assertEqual(front["eval_spec"]["dataset_ref"], "data:version:TODO")
            self.assertEqual(front["eval_spec"]["baseline"]["ref"], "run:TODO")
            self.assertEqual(front["eval_spec"]["metrics"][0]["name"], "TODO")

    def test_new_git_head_adds_current_commit_link(self) -> None:
        with self.runner.isolated_filesystem():
            self._run_git(["--version"])
            self._run_git(["init"])
            self._run_git(["config", "user.email", "test@example.com"])
            self._run_git(["config", "user.name", "Test User"])
            Path("tracked.txt").write_text("x\n", encoding="utf-8")
            self._run_git(["add", "tracked.txt"])
            self._run_git(["commit", "-m", "init"])
            head = self._run_git(["rev-parse", "--verify", "HEAD"]).stdout.strip()

            result = self.runner.invoke(
                app,
                [
                    "new",
                    "--title",
                    "Git Linked Decision",
                    "--stage",
                    "training",
                    "--type",
                    "generic",
                    "--owner",
                    "ahmet",
                    "--git-head",
                ],
            )
            self.assertEqual(result.exit_code, 0, msg=result.output)
            created = self._created_path(result.output)
            front = self._read_front_matter(created)

            self.assertEqual(
                front["links"],
                [
                    {
                        "id": "L-0001",
                        "rel": "implements",
                        "artifact_kind": "code",
                        "ref": f"git:commit:{head}",
                        "label": "Current HEAD commit",
                        "note": "",
                    }
                ],
            )

    def test_new_git_head_fails_without_git_head(self) -> None:
        with self.runner.isolated_filesystem():
            result = self.runner.invoke(
                app,
                [
                    "new",
                    "--title",
                    "Git Linked Decision",
                    "--stage",
                    "training",
                    "--type",
                    "generic",
                    "--owner",
                    "ahmet",
                    "--git-head",
                ],
            )
            self.assertEqual(result.exit_code, 2, msg=result.output)
            self.assertIn("FAIL GIT_HEAD_UNAVAILABLE", result.output)


if __name__ == "__main__":
    unittest.main()
