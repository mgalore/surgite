FROM node:22-slim AS frontend
WORKDIR /build/frontend
# Cache dependencies separately from frontend sources.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.14-slim
WORKDIR /app
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*
RUN pip install uv --quiet
# Cache dependencies before copying the package sources.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
RUN uv sync --frozen --no-dev
COPY --from=frontend /build/frontend/build /app/frontend/build
# Entrypoint repairs legacy volume ownership, then drops privileges.
RUN useradd -r -m -d /home/surgite surgite \
    && mkdir -p /var/surgite/repos /var/surgite/data \
    && chown -R surgite:surgite /app /var/surgite \
    && command -v setpriv >/dev/null \
    && chmod +x /app/entrypoint.sh
# setpriv preserves the environment, so correct root's HOME explicitly.
ENV HOME=/home/surgite
EXPOSE 8000
CMD ["/app/entrypoint.sh"]
