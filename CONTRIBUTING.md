# Contributing

Surgite favors small, maintainable changes: avoid dead code and speculative abstractions, keep one source of truth, use structured models for structured data, and prefer the fewest clear lines.

## Setup

Use Python 3.14+, Node.js 22+, Docker, [uv](https://docs.astral.sh/uv/), and [Task](https://taskfile.dev). Then:

```bash
uv sync --group dev
docker compose up -d db
uv run alembic upgrade head
cd frontend && npm install
```

Run the API with `uv run uvicorn surgite.api:app --reload` and the frontend with `cd frontend && npm run dev`. Copy `.env.example` when you need non-default configuration.

## Validate changes

Before opening a pull request, run the checks relevant to your change:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy surgite/
uv run pytest
uv lock --check
uv export --no-dev --no-hashes --no-emit-project | uv run pip-audit -r /dev/stdin
cd frontend && npm run check && npm run test && npm run build
task openapi-snapshot-check
```

Run `task openapi-snapshot` after changing a route or an endpoint description, and commit the updated snapshot. Add focused tests for behavior changes; keep existing tests readable and deterministic.

## Database and provider changes

Create Alembic migrations for schema changes and verify them on a populated development database. Never edit an applied migration. Document operator-visible upgrade steps in the relevant [migration guide](docs/migrations/).

Provider changes must preserve the shared provider interface, read credentials at call time, avoid logging secrets, and cover missing-key and provider-failure behavior.

## Pull requests

Keep pull requests focused. Explain the user-visible change, tests run, migrations or OpenAPI updates, and any operator action required. Update documentation when a public interface, configuration value, or deployment procedure changes.

Report suspected vulnerabilities privately under the [security policy](SECURITY.md), not in a public issue.
