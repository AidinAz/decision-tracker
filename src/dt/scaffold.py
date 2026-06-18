from __future__ import annotations

import re
from pathlib import Path

import typer

from dt.models import ScaffoldChanges
from dt.paths import _display_path
from dt.site import workflow_template


GITIGNORE_BLOCK = (
    "# >>> Decision Tracker generated outputs >>>\n"
    "_site/\n"
    "reports/\n"
    "decisions/index.json\n"
    "decisions/graph.json\n"
    "decisions/artifacts.json\n"
    "# <<< Decision Tracker generated outputs <<<\n"
)
GITIGNORE_START = "# >>> Decision Tracker generated outputs >>>"
GITIGNORE_END = "# <<< Decision Tracker generated outputs <<<"


def _write_scaffold_file(path: Path, content: str, force: bool, changes: ScaffoldChanges) -> None:
    if path.exists() and not force:
        changes.skipped.append(path.as_posix())
        return
    existed = path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    if existed and path.read_text(encoding="utf-8") == content:
        changes.unchanged.append(path.as_posix())
        return
    path.write_text(content, encoding="utf-8")
    (changes.replaced if existed else changes.created).append(path.as_posix())


def _touch_scaffold_file(path: Path, force: bool, changes: ScaffoldChanges) -> None:
    if path.exists() and not force:
        changes.skipped.append(path.as_posix())
        return
    existed = path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    if existed and path.read_text(encoding="utf-8") == "":
        changes.unchanged.append(path.as_posix())
        return
    path.write_text("", encoding="utf-8")
    (changes.replaced if existed else changes.created).append(path.as_posix())


def _write_gitignore(path: Path, changes: ScaffoldChanges) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(GITIGNORE_BLOCK, encoding="utf-8")
        changes.created.append(path.as_posix())
        return

    original = path.read_text(encoding="utf-8")
    has_start = GITIGNORE_START in original
    has_end = GITIGNORE_END in original
    if has_start and has_end:
        start = original.index(GITIGNORE_START)
        end = original.index(GITIGNORE_END, start) + len(GITIGNORE_END)
        updated = original[:start] + GITIGNORE_BLOCK.rstrip("\n") + original[end:]
        if not updated.endswith("\n"):
            updated += "\n"
    elif has_start or has_end:
        pattern = (
            rf"(?ms)^{re.escape(GITIGNORE_START)}.*$"
            if has_start
            else rf"(?ms)^.*{re.escape(GITIGNORE_END)}.*$"
        )
        updated = re.sub(pattern, GITIGNORE_BLOCK.rstrip("\n"), original, count=1)
        if not updated.endswith("\n"):
            updated += "\n"
    else:
        separator = "" if not original or original.endswith("\n") else "\n"
        updated = f"{original}{separator}\n{GITIGNORE_BLOCK}" if original.strip() else GITIGNORE_BLOCK

    if updated == original:
        changes.unchanged.append(path.as_posix())
        return

    path.write_text(updated, encoding="utf-8")
    changes.updated.append(path.as_posix())


def initialize_project(root: Path, force: bool) -> None:
    changes = ScaffoldChanges()

    try:
        (root / "decisions").mkdir(parents=True, exist_ok=True)
        (root / "docs").mkdir(parents=True, exist_ok=True)
        _touch_scaffold_file(root / "decisions" / ".gitkeep", force, changes)
        _write_gitignore(root / ".gitignore", changes)
        _write_scaffold_file(
            root / "docs" / "README.md",
            "# Decision support notes\n\nUse this directory for notes linked from Decision Records with `path:docs/...` refs.\n",
            force,
            changes,
        )
        _write_scaffold_file(root / ".github" / "workflows" / "pages.yml", workflow_template(), force, changes)
    except OSError as exc:
        typer.echo(f"FAIL INIT_IO_ERROR: {exc}")
        raise typer.Exit(code=2)

    for path in changes.created:
        typer.echo(f"Created {_display_path(path, root)}")
    for path in changes.replaced:
        typer.echo(f"Replaced {_display_path(path, root)}")
    for path in changes.updated:
        typer.echo(f"Updated {_display_path(path, root)}")
    for path in changes.unchanged:
        typer.echo(f"Unchanged {_display_path(path, root)}")
    for path in changes.skipped:
        typer.echo(f"Exists {_display_path(path, root)}")
    if not changes.created and not changes.replaced and not changes.updated and not changes.unchanged and not changes.skipped:
        typer.echo("No scaffold changes needed")
