#!/usr/bin/env bash
# Restore a backup by replacing the target database.
# Usage:
#   scripts/restore.sh path/to/surgite-20260101T120000Z.sql.gz
#   BACKUP_MODE=local BACKUP_PG_URL=... scripts/restore.sh ./backup.sql.gz

set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "usage: $0 <path-to-dump.sql.gz>" >&2
    exit 2
fi

DUMP="$1"
[[ -r "$DUMP" ]] || { echo "[restore] cannot read $DUMP" >&2; exit 1; }

MODE="${BACKUP_MODE:-docker}"
PROJECT="${COMPOSE_PROJECT_NAME:-$(basename "$(pwd)")}"
PG_USER="${POSTGRES_USER:-surgite}"
PG_DB="${POSTGRES_DB:-surgite}"

echo "[restore] reading $DUMP (mode=$MODE)"

run_restore() {
    gunzip -c "$DUMP" | "$@"
}

if [[ "$MODE" == "docker" ]]; then
    if ! command -v docker >/dev/null 2>&1; then
        echo "[restore] docker not found; set BACKUP_MODE=local or install docker" >&2
        exit 1
    fi
    DC="docker compose -p $PROJECT exec -T db"
    $DC psql -U "$PG_USER" -d postgres -v ON_ERROR_STOP=1 -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$PG_DB' AND pid <> pg_backend_pid();" >/dev/null
    $DC dropdb -U "$PG_USER" --if-exists "$PG_DB"
    $DC createdb -U "$PG_USER" "$PG_DB"
    run_restore $DC psql -U "$PG_USER" -d "$PG_DB" -v ON_ERROR_STOP=1
elif [[ "$MODE" == "local" ]]; then
    if [[ -z "${BACKUP_PG_URL:-}" ]]; then
        echo "[restore] BACKUP_MODE=local requires BACKUP_PG_URL" >&2
        exit 1
    fi
    ADMIN_URL="${BACKUP_PG_URL_ADMIN:-${BACKUP_PG_URL%/surgite}/postgres}"
    psql "$ADMIN_URL" -v ON_ERROR_STOP=1 -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$PG_DB' AND pid <> pg_backend_pid();" >/dev/null
    dropdb "${BACKUP_PG_URL%/*}/$PG_DB" 2>/dev/null || true
    createdb "${BACKUP_PG_URL%/*}/$PG_DB"
    run_restore psql "$BACKUP_PG_URL" -v ON_ERROR_STOP=1
else
    echo "[restore] unknown BACKUP_MODE: $MODE" >&2
    exit 1
fi

echo "[restore] done"
