import os
import re
import subprocess
from datetime import date
from pathlib import Path

from surgite.models import Commit

REMOTE_PATTERNS = re.compile(r"^(https?://|git@|git://|ssh://)")


def is_remote_url(path: str) -> bool:
    """Return whether a path looks like a remote Git URL."""
    return bool(REMOTE_PATTERNS.match(path))


def _repo_name_from_url(url: str) -> str:
    """Extract a repository name from a remote URL."""
    name = url.rstrip("/")
    if name.endswith(".git"):
        name = name[:-4]
    if ":" in name and not name.startswith("http"):
        name = name.split(":")[-1]
    name = name.rstrip("/").split("/")[-1]
    return name


def ensure_repo(name: str, url: str, cache_dir: str, timeout: int = 120) -> str:
    """Clone or update a metadata-only repository cache."""
    dest = os.path.join(cache_dir, name)
    Path(cache_dir).mkdir(parents=True, exist_ok=True)

    if os.path.isdir(os.path.join(dest, ".git")):
        subprocess.run(
            ["git", "fetch", "origin"],
            cwd=dest,
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout,
        )
        # Refresh origin/HEAD in case the default branch changed.
        subprocess.run(
            ["git", "remote", "set-head", "origin", "-a"],
            cwd=dest,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        subprocess.run(
            ["git", "reset", "--soft", "origin/HEAD"],
            cwd=dest,
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout,
        )
    else:
        subprocess.run(
            ["git", "clone", "--filter=blob:none", "--no-checkout", url, dest],
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout,
        )
    return dest


def ls_remote(url: str, timeout: int = 10) -> None:
    """Check remote reachability without cloning."""
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--heads", url],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"git ls-remote timed out after {timeout}s") from exc
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git ls-remote failed")


def _is_git_ref(repo_path: str, value: str, timeout: int = 120) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", value],
        capture_output=True,
        cwd=repo_path,
        timeout=timeout,
    )
    return result.returncode == 0


def get_raw_log(
    repo_path: str,
    since: str,
    until: str,
    author: str | None = None,
    since_commit: str | None = None,
    timeout: int = 120,
) -> str:
    """Return the requested raw Git log."""
    cmd = ["git", "log", "--pretty=format:%H\x1f%ad\x1f%an\x1f%s", "--date=short"]

    until_is_ref = _is_git_ref(repo_path, until, timeout)

    if since_commit:
        if until_is_ref:
            cmd.append(f"{since_commit}..{until}")
        else:
            cmd.append(f"{since_commit}..")
            cmd.append(f"--until={until}")
    else:
        if until_is_ref:
            cmd.append(until)
            cmd.append(f"--since={since}")
        else:
            cmd.append(f"--since={since}")
            cmd.append(f"--until={until}")

    if author:
        cmd.append(f"--author={author}")

    result = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        cwd=repo_path,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    return result.stdout


def parse_log(raw_log: str) -> list[Commit]:
    """Parse raw Git log records into commits."""
    lines = raw_log.splitlines()
    commits = []
    for line in lines:
        hash, date_str, author, message = line.split("\x1f", maxsplit=3)
        commits.append(
            Commit(
                hash=hash,
                date=date.fromisoformat(date_str),
                author=author,
                message=message,
            )
        )
    return commits
