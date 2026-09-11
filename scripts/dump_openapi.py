"""Write a deterministic OpenAPI document for snapshot checks."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

# Configure imports to avoid external services and background work.
_DEFAULT_DB = Path("/tmp/surgite_openapi_dump.db")
if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = f"sqlite:///{_DEFAULT_DB}"
os.environ.setdefault("AUTH_MODE", "off")
os.environ.setdefault("INGEST_INTERVAL", "0")
os.environ.setdefault("GROQ_API_KEY", "")
os.environ.setdefault("DEEPSEEK_API_KEY", "")
os.environ.setdefault("ANTHROPIC_API_KEY", "")
os.environ.setdefault("LOCAL_API_KEY", "")
os.environ.setdefault("LLM_LOCAL_ONLY", "")

from surgite.api import app  # noqa: E402


def _normalise(obj: Any) -> Any:
    """Recursively sort mappings and normalize sequences."""
    if isinstance(obj, Mapping):
        return {k: _normalise(obj[k]) for k in sorted(obj)}
    if isinstance(obj, (list, tuple)):
        return [_normalise(item) for item in obj]
    return obj


def _sort_paths(document: Mapping[str, Any]) -> Mapping[str, Any]:
    """Sort OpenAPI paths by URL."""
    if "paths" not in document:
        return document
    result = dict(document)
    result["paths"] = {url: document["paths"][url] for url in sorted(document["paths"])}
    return result


def _strip_volatile_fields(document: Mapping[str, Any]) -> Mapping[str, Any]:
    """Remove per-process fields that would destabilize snapshots."""
    result = dict(document)
    for field in ("servers", "info"):
        info = result.get(field)
        if isinstance(info, Mapping):
            cleaned = {k: v for k, v in info.items() if k not in {"x-build-id", "x-process-id"}}
            result[field] = cleaned
    return result


def dump() -> str:
    """Return the normalised OpenAPI document as a JSON string."""
    raw = app.openapi()
    normalised = _normalise(raw)
    sorted_paths = _sort_paths(normalised)
    stripped = _strip_volatile_fields(sorted_paths)
    return json.dumps(stripped, indent=2, sort_keys=False, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dump the canonical OpenAPI document for surgite.")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Write the dump to this file. Default: stdout.",
    )
    args = parser.parse_args(argv)

    try:
        text = dump()
    except Exception as exc:  # noqa: BLE001 — we want to surface the raw error
        print(f"dump_openapi: failed to generate the OpenAPI document: {exc}", file=sys.stderr)
        return 1

    if args.output is None:
        sys.stdout.write(text)
    else:
        try:
            args.output.write_text(text, encoding="utf-8")
        except OSError as exc:
            print(f"dump_openapi: failed to write {args.output}: {exc}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
