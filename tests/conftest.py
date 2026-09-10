"""Shared test configuration and fixtures."""

import os
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path

_db_file = Path(tempfile.gettempdir()) / "surgite_test.db"
if _db_file.exists():
    _db_file.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{_db_file}"
# Set import-time configuration before importing surgite.
os.environ["GROQ_API_KEY"] = ""
os.environ["DEEPSEEK_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["LOCAL_API_KEY"] = ""
os.environ["LOCAL_BASE_URL"] = ""
os.environ["LLM_LOCAL_ONLY"] = ""
os.environ["INGEST_INTERVAL"] = "0"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select

from surgite.api import app
from surgite.auth import ensure_bootstrap_user
from surgite.db import (
    ApiKeyRow,
    AuditLogRow,
    Base,
    CommitRow,
    InviteRow,
    OrgMemberRow,
    OrgRow,
    PromptSettingsRow,
    ProviderKeyRow,
    RepoRow,
    SessionRow,
    SharedSummaryRow,
    UserRow,
    engine,
    get_session,
)


@event.listens_for(engine, "connect")
def _set_sqlite_fk(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def _clean_tables():
    yield
    with get_session() as s:
        # Delete in foreign-key order.
        s.query(CommitRow).delete()
        s.query(SharedSummaryRow).delete()
        s.query(PromptSettingsRow).delete()
        s.query(RepoRow).delete()
        s.query(ProviderKeyRow).delete()
        s.query(ApiKeyRow).delete()
        s.query(AuditLogRow).delete()
        s.query(SessionRow).delete()
        s.query(InviteRow).delete()
        s.query(OrgMemberRow).delete()
        s.query(UserRow).delete()
        s.query(OrgRow).delete()
        s.commit()


@pytest.fixture(autouse=True)
def _reset_rate_limit_buckets():
    from surgite import rate_limit

    rate_limit._reset_for_tests()
    yield
    rate_limit._reset_for_tests()


@pytest.fixture(autouse=True)
def _reset_active_ingests():
    from surgite import api

    with api._active_ingests_lock:
        api._active_ingests.clear()
    yield
    with api._active_ingests_lock:
        api._active_ingests.clear()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def client_with_scheduler(monkeypatch):
    """Run TestClient with the one-second ingest scheduler enabled."""
    monkeypatch.setenv("INGEST_INTERVAL", "1")
    with TestClient(app) as c:
        yield c


@pytest.fixture
def add_commit():
    def _add(**overrides):
        repo_name = overrides.pop("repo", "demo")
        repo_id = overrides.pop("repo_id", None)
        owner_id = overrides.pop("owner_id", None)
        defaults = {
            "hash": "a" * 40,
            "short_hash": "aaaaaaa",
            "date": date(2026, 5, 19),
            "author": "Alice",
            "message": "init",
            "repo": repo_name,
            "ingested_at": datetime.now(UTC),
        }
        defaults.update(overrides)
        with get_session() as s:
            if owner_id is None:
                owner_id = ensure_bootstrap_user(s).id
            if repo_id is None:
                repo = s.scalar(select(RepoRow).where(RepoRow.name == repo_name))
                if repo is None:
                    repo = RepoRow(
                        name=repo_name,
                        clone_url=f"https://example.com/{repo_name}.git",
                        owner_id=owner_id,
                    )
                    s.add(repo)
                    s.flush()
                repo_id = repo.id
            s.add(CommitRow(repo_id=repo_id, owner_id=owner_id, **defaults))
            s.commit()

    return _add


@pytest.fixture
def add_repo():
    def _add(**overrides):
        owner_id = overrides.pop("owner_id", None)
        defaults = {
            "name": "demo",
            "clone_url": "https://example.com/demo.git",
            "added_at": datetime.now(UTC),
            "last_ingested_at": None,
        }
        defaults.update(overrides)
        with get_session() as s:
            if owner_id is None:
                owner_id = ensure_bootstrap_user(s).id
            repo = RepoRow(owner_id=owner_id, **defaults)
            s.add(repo)
            s.commit()
            s.refresh(repo)
            return repo.id

    return _add
