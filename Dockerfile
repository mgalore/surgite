FROM node:22-slim AS frontend
WORKDIR /build/frontend
# npm ci keyed on the manifests alone, so a .svelte edit reuses node_modules.
# The `prepare` script's svelte-kit sync has no config to read yet; its
# `|| echo ''` guard makes that harmless, and `vite build` syncs anyway.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.14-slim
WORKDIR /app
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*
RUN pip install uv --quiet
# Deps install from the manifests alone, so a source edit below reuses this
# layer. --no-install-project is load-bearing: surgite is not here yet, and a
# plain `uv sync` fails on that -- which is what reverted this split in 6b525b0.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
# Installs surgite itself; deps are already in .venv, which survives the COPY
# because .dockerignore excludes it.
RUN uv sync --frozen --no-dev
COPY --from=frontend /build/frontend/build /app/frontend/build
# Run as an unprivileged user. The app binds port 8000 (above the privileged
# range) and touches only /app and the two /var/surgite mounts, so root is not
# needed. The image still starts as root so entrypoint.sh can repair the
# ownership of volumes populated by an older root-running image; it drops to
# `surgite` via setpriv before running anything. `command -v setpriv` fails
# the build here rather than at container start if util-linux ever stops
# shipping in the base image.
RUN useradd -r -m -d /home/surgite surgite \
    && mkdir -p /var/surgite/repos /var/surgite/data \
    && chown -R surgite:surgite /app /var/surgite \
    && command -v setpriv >/dev/null \
    && chmod +x /app/entrypoint.sh
# setpriv does not reset the environment, and Docker sets HOME=/root for uid 0.
# Without this the app keeps root's HOME after the drop, so anything reaching
# for $HOME -- git config, credential helpers -- writes to a directory it does
# not own.
ENV HOME=/home/surgite
EXPOSE 8000
CMD ["/app/entrypoint.sh"]
