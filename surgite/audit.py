"""Non-fatal audit logging."""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from surgite.db import AuditLogRow, UserRow, session_scope

log = logging.getLogger("audit")


def _truncate(value: str | None, limit: int) -> str | None:
    if not value:
        return None
    return value[:limit]


def audit(
    action: str,
    *,
    actor_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    metadata: dict[str, Any] | None = None,
    session: Session | None = None,
) -> None:
    """Persist and emit a security-relevant event."""
    row = AuditLogRow(
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=_truncate(target_id, 64),
        ip=_truncate(ip, 64),
        user_agent=_truncate(user_agent, 256),
        metadata_=metadata,
    )
    try:
        with session_scope(session) as s:
            if actor_id is not None:
                row.org_id = s.scalar(select(UserRow.personal_org_id).where(UserRow.id == actor_id))
            s.add(row)
            s.commit()
    except Exception as exc:  # noqa: BLE001 — audit must never break the caller
        log.error("audit write failed: %s", exc, extra={"action": action})
    log.info(
        "audit %s actor=%s target=%s:%s",
        action,
        actor_id or "-",
        target_type or "-",
        target_id or "-",
    )
