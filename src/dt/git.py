from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dt.models import DiscoverCandidate


class GitLogError(RuntimeError):
    """Raised when discover cannot inspect local Git history."""


@dataclass(frozen=True)
class GitCommitCheck:
    status: str
    detail: str = ""


def _keyword_matches(message: str, keywords: list[str]) -> bool:
    for keyword in keywords:
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(keyword)}(?![A-Za-z0-9])", message):
            return True
    return False


def _git_repo_root(root: Path) -> Optional[Path]:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip()).resolve()


def _resolve_git_head(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("git executable was not found") from exc
    except subprocess.SubprocessError as exc:
        raise RuntimeError("git command failed while resolving HEAD") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or "not a Git repository or HEAD does not exist"
        raise RuntimeError(detail)
    return result.stdout.strip()


def _git_commit_check(root: Path, sha: str) -> GitCommitCheck:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "cat-file", "-e", f"{sha}^{{commit}}"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except FileNotFoundError:
        return GitCommitCheck("unavailable", "git executable was not found")
    except subprocess.TimeoutExpired:
        return GitCommitCheck("unavailable", "git commit check timed out")
    except subprocess.SubprocessError:
        return GitCommitCheck("unavailable", "git command failed while checking commit")
    if result.returncode == 0:
        return GitCommitCheck("exists")
    stderr = result.stderr.strip()
    missing_markers = ("not a valid object name", "could not get object info", "bad object")
    if result.returncode == 1 or any(marker in stderr.lower() for marker in missing_markers):
        return GitCommitCheck("missing")
    detail = stderr or "git command failed while checking commit"
    return GitCommitCheck("unavailable", detail)


def _git_commit_exists(root: Path, sha: str) -> bool:
    return _git_commit_check(root, sha).status == "exists"


def _infer_discover_stage(message: str) -> str:
    lower = message.lower()
    if any(term in lower for term in ("dataset", "data", "dvc", "checksum")):
        return "data"
    if any(term in lower for term in ("evaluation", "metric", "threshold", "protocol", "split")):
        return "evaluation"
    if any(term in lower for term in ("deploy", "serve", "production", "release")):
        return "deployment"
    if any(term in lower for term in ("monitor", "drift", "alert")):
        return "monitoring"
    return "training"


def _infer_discover_type(message: str) -> str:
    lower = message.lower()
    if any(term in lower for term in ("evaluation", "metric", "threshold", "protocol", "split")):
        return "evaluation_protocol"
    if any(term in lower for term in ("model", "baseline", "fine-tune", "hyperparameter", "transformer")):
        return "model"
    return "generic"


def _git_log_candidates(root: Path, keywords: list[str], since: Optional[str], limit: int) -> list[DiscoverCandidate]:
    command = ["git", "-C", str(root), "log", "--pretty=format:%H%x09%s"]
    if since:
        command.append(f"--since={since}")
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=5, check=False)
    except FileNotFoundError as exc:
        raise GitLogError("git executable was not found") from exc
    except subprocess.SubprocessError as exc:
        raise GitLogError("git log failed while scanning history") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or "git log failed"
        raise GitLogError(detail)

    normalized_keywords = [keyword.lower() for keyword in keywords if keyword.strip()]
    candidates: list[DiscoverCandidate] = []
    for line in result.stdout.splitlines():
        if "\t" not in line:
            continue
        sha, subject = line.split("\t", 1)
        subject_lower = subject.lower()
        if not _keyword_matches(subject_lower, normalized_keywords):
            continue
        candidates.append(
            DiscoverCandidate(
                sha=sha,
                title=subject.strip(),
                stage=_infer_discover_stage(subject),
                decision_type=_infer_discover_type(subject),
            )
        )
        if len(candidates) >= limit:
            break
    return candidates
