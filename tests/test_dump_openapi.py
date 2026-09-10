"""Tests for the deterministic OpenAPI snapshot."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "dump_openapi.py"


@pytest.fixture(scope="module")
def dump_output() -> str:
    """Cache one end-to-end dump for the module."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, (
        f"dump_openapi.py exited {result.returncode}\n"
        f"--- stdout ---\n{result.stdout[:500]}\n"
        f"--- stderr ---\n{result.stderr[:1000]}"
    )
    return result.stdout


def test_dump_is_valid_json(dump_output: str) -> None:
    parsed = json.loads(dump_output)
    assert isinstance(parsed, dict)


def test_dump_has_openapi_required_keys(dump_output: str) -> None:
    parsed = json.loads(dump_output)
    assert "openapi" in parsed, "missing required 'openapi' key"
    assert "info" in parsed, "missing required 'info' key"
    assert "paths" in parsed, "missing required 'paths' key"
    assert re.match(r"^\d+\.\d+\.\d+$", parsed["openapi"]), (
        f"unexpected openapi version: {parsed['openapi']!r}"
    )


def test_dump_documents_expected_routes(dump_output: str) -> None:
    parsed = json.loads(dump_output)
    paths = parsed["paths"]
    for expected in (
        "/auth/login",
        "/auth/logout",
        "/auth/me",
        "/summary",
        "/summary/stream",
        "/commits",
        "/repos",
        "/providers",
        "/health",
        "/health/deep",
    ):
        assert expected in paths, f"expected route {expected!r} missing from OpenAPI dump"


def test_dump_operation_ids_are_unique_and_stable(dump_output: str) -> None:
    import re
    from collections import Counter

    parsed = json.loads(dump_output)
    ids: list[str] = []
    for path, methods in parsed["paths"].items():
        for method, op in methods.items():
            if method == "parameters":
                continue
            op_id = op.get("operationId", "")
            assert op_id, f"route {method.upper()} {path} has empty operationId"
            ids.append(op_id)

    counts = Counter(ids)
    duplicates = {op_id: n for op_id, n in counts.items() if n > 1}
    assert not duplicates, f"duplicate operationIds: {duplicates}"

    invalid = [op_id for op_id in ids if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", op_id)]
    assert not invalid, f"operationIds with invalid characters: {invalid}"


def test_dump_is_byte_stable(dump_output: str, tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    first.write_text(dump_output, encoding="utf-8")
    second = tmp_path / "second.json"
    subprocess.run(
        [sys.executable, str(SCRIPT), "--output", str(second)],
        capture_output=True,
        text=True,
        check=True,
        cwd=REPO_ROOT,
    )
    assert first.read_bytes() == second.read_bytes(), (
        "two consecutive dump runs produced different output — "
        "the dump is not byte-stable; this will cause the "
        "snapshot gate to false-positive on every run"
    )


def test_dump_paths_are_sorted(dump_output: str) -> None:
    parsed = json.loads(dump_output)
    paths = list(parsed["paths"].keys())
    assert paths == sorted(paths), (
        f"paths are not URL-sorted; the diff will be unreadable.\n"
        f"first 5: {paths[:5]}\n"
        f"sorted:   {sorted(paths)[:5]}"
    )


def test_dump_output_flag_writes_to_file(dump_output: str, tmp_path: Path) -> None:
    target = tmp_path / "snapshot.json"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--output", str(target)],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, f"dump failed: {result.stderr}"
    assert target.exists(), "--output did not create the target file"
    assert target.read_text(encoding="utf-8") == dump_output, (
        "--output file content differs from stdout content"
    )
    assert result.stdout == "", (
        f"--output should not write to stdout, but got: {result.stdout[:200]!r}"
    )
