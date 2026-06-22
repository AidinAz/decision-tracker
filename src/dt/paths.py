from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

import yaml

from dt.constants import ID_RE
from dt.markdown import _extract_front_matter


def _discover_project_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "decisions").exists():
            return candidate
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return start


def _resolve_root(root: Optional[Path]) -> Path:
    if root is not None:
        return root.resolve()
    return _discover_project_root(Path.cwd().resolve())


def _json_dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_text(rendered, encoding="utf-8")


def _display_path(path: str, root: Path) -> str:
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            return candidate.relative_to(root).as_posix()
        except ValueError:
            return candidate.as_posix()
    return path


def _slugify_title(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "untitled"


def _next_decision_id(decisions_dir: Path) -> str:
    max_id = 0
    for path in sorted(decisions_dir.glob("DR-*.md"), key=lambda p: p.name):
        candidate: Optional[str] = None
        try:
            text = path.read_text(encoding="utf-8")
            yaml_text, _ = _extract_front_matter(text)
            doc = yaml.safe_load(yaml_text)
            if isinstance(doc, dict) and isinstance(doc.get("id"), str) and ID_RE.match(doc["id"]):
                candidate = doc["id"]
        except (ValueError, yaml.YAMLError):
            candidate = None
        if candidate is None:
            match = re.match(r"^(DR-\d{4})", path.stem)
            if match:
                candidate = match.group(1)
        if candidate is not None:
            max_id = max(max_id, int(candidate.split("-")[1]))
    next_id = max_id + 1
    if next_id > 9999:
        raise ValueError("maximum decision id DR-9999 has been reached")
    return f"DR-{next_id:04d}"
