#!/usr/bin/env bash
# Write and rotate gzip-compressed Postgres dumps.

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
KEEP="${BACKUP_KEEP:-14}"
MODE="${BACKUP_MODE:-docker}"
PROJECT="${COMPOSE_PROJECT_NAME:-$(basename "$(pwd)")}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
FILENAME="surgite-${TS}.sql.gz"
TARGET="${BACKUP_DIR}/${FILENAME}"

mkdir -p "$BACKUP_DIR"

echo "[backup] writing $TARGET (mode=$MODE)"

if [[ "$MODE" == "docker" ]]; then
    if ! command -v docker >/dev/null 2>&1; then
        echo "[backup] docker not found on PATH; set BACKUP_MODE=local or install docker" >&2
        exit 1
    fi
    docker compose -p "$PROJECT" exec -T db \
        pg_dump -U "${POSTGRES_USER:-surgite}" -d "${POSTGRES_DB:-surgite}" --no-owner \
        | gzip -9 > "$TARGET"
elif [[ "$MODE" == "local" ]]; then
    if [[ -z "${BACKUP_PG_URL:-}" ]]; then
        echo "[backup] BACKUP_MODE=local requires BACKUP_PG_URL" >&2
        exit 1
    fi
    pg_dump "$BACKUP_PG_URL" --no-owner | gzip -9 > "$TARGET"
else
    echo "[backup] unknown BACKUP_MODE: $MODE" >&2
    exit 1
fi

echo "[backup] wrote $(du -h "$TARGET" | cut -f1)"

# Keep the newest $KEEP dumps.
if [[ -d "$BACKUP_DIR" ]]; then
    mapfile -t OLD < <(ls -1t "$BACKUP_DIR"/surgite-*.sql.gz 2>/dev/null | tail -n +$((KEEP + 1)) || true)
    for f in "${OLD[@]:-}"; do
        [[ -n "$f" ]] && rm -f -- "$f" && echo "[backup] pruned $f"
    done
fi

echo "[backup] done"
