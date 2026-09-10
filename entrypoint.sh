#!/bin/sh
set -e

# Repair legacy root-owned volumes before dropping privileges.
if [ "$(id -u)" = "0" ]; then
    for d in /var/surgite/repos /var/surgite/data; do
        [ "$(stat -c %U "$d")" = surgite ] || chown -R surgite:surgite "$d"
    done
    setpriv --reuid=surgite --regid=surgite --init-groups \
        /app/.venv/bin/alembic upgrade head
    exec setpriv --reuid=surgite --regid=surgite --init-groups \
        /app/.venv/bin/uvicorn surgite.api:app --host 0.0.0.0 --port 8000
fi

# Support containers started with an explicit non-root user.
/app/.venv/bin/alembic upgrade head
exec /app/.venv/bin/uvicorn surgite.api:app --host 0.0.0.0 --port 8000
