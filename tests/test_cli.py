"""CLI argument and output tests."""

import builtins
import importlib.metadata
import sys

import pytest

from surgite import cli
from surgite.cli import _resolve_since, main


def test_version_flag_prints_the_installed_version(capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["surgite", "--version"])

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 0
    assert importlib.metadata.version("surgite") in capsys.readouterr().out


def test_version_flag_is_listed_in_help(capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["surgite", "--help"])

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 0
    assert "--version" in capsys.readouterr().out


def test_resolve_since_translates_git_relative_dates():
    from datetime import date, timedelta

    assert _resolve_since("7.days.ago") == (date.today() - timedelta(days=7)).isoformat()
    assert _resolve_since("2.weeks.ago") == (date.today() - timedelta(days=14)).isoformat()


def test_resolve_since_passes_through_iso_dates():
    assert _resolve_since("2026-08-01") == "2026-08-01"


def test_resolve_since_defaults_to_7_days():
    from datetime import date, timedelta

    assert _resolve_since(None) == (date.today() - timedelta(days=7)).isoformat()


def test_output_is_written_as_utf8(monkeypatch, tmp_path):
    summary = "fix: café → 日本語 🎉"
    out = tmp_path / "summary.txt"
    open_kwargs = []
    real_open = builtins.open

    def recording_open(*args, **kwargs):
        open_kwargs.append(kwargs)
        return real_open(*args, **kwargs)

    monkeypatch.setattr(builtins, "open", recording_open)
    monkeypatch.setattr(cli, "_run_local", lambda args: summary)
    monkeypatch.setattr(sys, "argv", ["surgite", "some/repo", "--output", str(out)])

    main()

    assert {"encoding": "utf-8"} in open_kwargs
    assert out.read_text(encoding="utf-8") == summary
