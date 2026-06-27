from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Optional


def _round3(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_non_empty_mapping(value: Any) -> bool:
    return isinstance(value, dict) and bool(value)


def _is_non_empty_section(value: Optional[str]) -> bool:
    return bool(value and value.strip())


def _stable_stakeholders(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    dedup: dict[str, str] = {}
    for raw in values:
        if not isinstance(raw, str):
            continue
        clean = raw.strip()
        if not clean:
            continue
        key = clean.lower()
        if key not in dedup:
            dedup[key] = clean
    return sorted(dedup.values(), key=lambda v: v.lower())


def _parse_stakeholders_csv(raw: str) -> list[str]:
    if not raw.strip():
        return []
    dedup: dict[str, str] = {}
    for piece in raw.split(","):
        clean = piece.strip()
        if not clean:
            continue
        key = clean.lower()
        if key not in dedup:
            dedup[key] = clean
    return list(dedup.values())


def _parse_list_text(raw: str, separator: str = ",") -> list[str]:
    if not raw.strip():
        return []
    values: list[str] = []
    seen: set[str] = set()
    for piece in raw.split(separator):
        clean = piece.strip()
        if not clean:
            continue
        key = clean.lower()
        if key not in seen:
            seen.add(key)
            values.append(clean)
    return values


def _record_file_suffix(record_path: Path, root: Path) -> str:
    try:
        display = record_path.relative_to(root).as_posix()
    except ValueError:
        display = record_path.as_posix()
    return f" [file: {display}]"
