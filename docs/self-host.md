# Self-hosting surgite

Surgite runs as a FastAPI application with PostgreSQL. Docker Compose is the supported local deployment path; see [`.env.example`](../.env.example) for every setting.

## Start

```bash
git clone https://github.com/nicoleman0/surgite.git
cd surgite
cp .env.example .env
# For multi-user access, set AUTH_MODE=multi_user and BOOTSTRAP_OWNER_EMAIL.
docker compose up -d
docker compose logs -f app
```

In multi-user mode, first start prints a one-time owner invite. Redeem it from the web interface or with:

```bash
uv run surgite --redeem-invite <token> --email you@example.com
```

Use the published image instead of building locally by setting `APP_IMAGE=ghcr.io/nicoleman0/surgite:latest` in `.env`. To upgrade an image deployment, run `docker compose pull && docker compose up -d`.

## Configuration

### LLM provider

Set `LLM_PROVIDER` and its matching API key. For a self-hosted OpenAI-compatible server:

```dotenv
LLM_PROVIDER=local
LOCAL_BASE_URL=http://llm.internal:8000/v1
LOCAL_API_KEY=optional-key
# Set LOCAL_MODEL when the server exposes more than one model.
```

`LOCAL_BASE_URL` must be reachable from the app container. Set `LLM_LOCAL_ONLY=1` to expose only the local provider. Keep `LOCAL_MODEL` unset only when the server lists exactly one model.

### Repository sync

`INGEST_INTERVAL` controls periodic syncs; set it to `0` to disable them. Use `INGEST_CONCURRENCY` and `GIT_TIMEOUT_SECONDS` to bound concurrent Git work and slow remotes.

### HTTPS and proxies

Multi-user browser sessions require HTTPS. Terminate TLS in front of the application using your existing infrastructure; the app itself can listen on plain HTTP behind that terminator. Do not expose a development deployment with `DEBUG=true`.

If the proxy sends `X-Forwarded-For`, set `TRUSTED_PROXIES` to only the direct proxy IP addresses or CIDRs. Otherwise leave it empty: trusting arbitrary forwarded headers lets clients evade the IP rate-limit backstop.

For private certificate authorities, mount the CA bundle and set `SSL_CERT_FILE` for outbound HTTPS or `GIT_SSL_CAINFO` for Git. Avoid `GIT_SSL_NO_VERIFY=1`; it disables Git TLS verification.

### Email

Set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_TLS`, and `PUBLIC_URL` to deliver password-reset links. Delivery failures are logged; the initial owner invite is always available in application logs.

## Backups and encryption keys

Back up PostgreSQL and the secret-encryption key independently. The Compose scripts cover database dumps:

```bash
./scripts/backup.sh
./scripts/restore.sh /path/to/backup.sql.gz
```

`BACKUP_KEEP` controls retained dumps. Provider keys stored in the database are encrypted with `SECRETS_ENCRYPTION_KEY`; if it is unset, Compose persists a generated key at `SECRETS_KEY_FILE`. Losing both the database copy and that key makes encrypted provider keys unrecoverable. Store an explicit `SECRETS_ENCRYPTION_KEY` or a secure backup of the key file outside the deployment volume.

Deployments upgrading from 1.0.1 or earlier must preserve the old `/app/.secrets_key` before replacing the container. Copy its contents into `SECRETS_ENCRYPTION_KEY`, redeploy, and keep the value backed up.

## Upgrades

For a source deployment:

```bash
git pull --ff-only
docker compose up -d --build
```

The container applies database migrations on startup. Read the applicable [migration guides](migrations/) before crossing a listed release boundary, and take a database backup first.

## Runbook

- Check application health and logs with `docker compose ps` and `docker compose logs app`.
- Keep the database and encryption-key backups recoverable before upgrades or host changes.
- Restrict repository registration to remotes and Git hooks you trust; ingestion executes Git against those repositories.
- Rotate a provider key by updating it through the authenticated settings endpoint or web UI, then verify a summary request.
