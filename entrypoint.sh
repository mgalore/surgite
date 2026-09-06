#!/bin/sh
set -e

# Run as an unprivileged user. The image's default user is root so that we can
# repair the ownership of pre-existing volumes here (a named volume populated
# by an older root-running image is root-owned). After the repair we drop to
# `surgite` with setpriv for the lifetime of the container.
if [ "$(id -u)" = "0" ]; then
    # /app is chowned at build time, so only the mounts can be wrong here, and
    # only when the volume predates the unprivileged image. Guarding the walk
    # matters: a populated repo cache is thousands of git objects, and this
    # runs on every container start.
    #
    # ponytail: tests the mount root's owner only. That is the case this
    # exists for -- a whole volume left root-owned by an older image. A tree
    # that is half-chowned needs a manual `chown -R`.
    for d in /var/surgite/repos /var/surgite/data; do
        [ "$(stat -c %U "$d")" = surgite ] || chown -R surgite:surgite "$d"
    done
    setpriv --reuid=surgite --regid=surgite --init-groups \
        /app/.venv/bin/alembic upgrade head
    exec setpriv --reuid=surgite --regid=surgite --init-groups \
        /app/.venv/bin/uvicorn surgite.api:app --host 0.0.0.0 --port 8000
fi

# Already unprivileged (e.g. `docker run --user 1000`): run directly.
# alembic is a one-shot migration and must complete before uvicorn starts;
# uvicorn replaces this shell so the container's PID 1 is the app itself.
/app/.venv/bin/alembic upgrade head
exec /app/.venv/bin/uvicorn surgite.api:app --host 0.0.0.0 --port 8000
