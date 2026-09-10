"""Model-agnostic commit summarization over HTTP."""

import asyncio
import json
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx
from sqlalchemy import select

_TIMEOUT = 120.0
_MAX_TOKENS = 1024
_MAX_PARALLEL_SUMMARIES = 4
DEFAULT_PROVIDER = "anthropic"
# Self-hosted model discovery is cached for the process lifetime.
_discovered_models: dict[str, str] = {}

_TONE_INSTRUCTIONS: dict[str, str] = {
    "neutral": "Write in plain, neutral language. Do not use first person.",
    "first-person": "Write in first person (I/we).",
    "formal": "Write in formal, professional language. Do not use first person.",
    "casual": "Write in a casual, conversational tone.",
}


class ProviderError(Exception):
    """Provider is unknown or its API key is not configured."""


@dataclass(frozen=True)
class Provider:
    name: str
    kind: str  # "openai" (GROQ/DeepSeek/self-hosted) or "anthropic"
    default_base_url: str
    key_env: str
    url_env: str
    model_env: str
    default_model: str

    @property
    def api_key(self) -> str | None:
        return os.environ.get(self.key_env) or None

    @property
    def base_url(self) -> str:
        return os.environ.get(self.url_env) or self.default_base_url

    def model(self, override: str | None = None) -> str:
        """Return the overridden, configured, default, or discovered model."""
        return (
            override
            or os.environ.get(self.model_env)
            or self.default_model
            or _discovered_models.get(self.base_url, "")
        )


_ALL_PROVIDERS: dict[str, Provider] = {
    "groq": Provider(
        name="groq",
        kind="openai",
        default_base_url="https://api.groq.com/openai/v1",
        key_env="GROQ_API_KEY",
        url_env="GROQ_BASE_URL",
        model_env="GROQ_MODEL",
        default_model="llama-3.1-8b-instant",
    ),
    "deepseek": Provider(
        name="deepseek",
        kind="openai",
        default_base_url="https://api.deepseek.com",
        key_env="DEEPSEEK_API_KEY",
        url_env="DEEPSEEK_BASE_URL",
        model_env="DEEPSEEK_MODEL",
        default_model="deepseek-chat",
    ),
    "anthropic": Provider(
        name="anthropic",
        kind="anthropic",
        default_base_url="https://api.anthropic.com",
        key_env="ANTHROPIC_API_KEY",
        url_env="ANTHROPIC_BASE_URL",
        model_env="ANTHROPIC_MODEL",
        default_model="claude-haiku-4-5-20251001",
    ),
    "local": Provider(
        name="local",
        kind="openai",
        default_base_url="",
        key_env="LOCAL_API_KEY",
        url_env="LOCAL_BASE_URL",
        model_env="LOCAL_MODEL",
        default_model="",
    ),
}


def _visible(providers: dict[str, Provider]) -> dict[str, Provider]:
    """Restrict the registry to local inference when configured."""
    if os.environ.get("LLM_LOCAL_ONLY", "").lower() in {"1", "true", "yes"}:
        return {"local": providers["local"]}
    return providers


PROVIDERS: dict[str, Provider] = _visible(_ALL_PROVIDERS)


def default_provider() -> str:
    env = os.environ.get("LLM_PROVIDER")
    if env:
        return env.lower()
    return DEFAULT_PROVIDER if DEFAULT_PROVIDER in PROVIDERS else next(iter(PROVIDERS))


def resolve_provider(name: str | None) -> Provider:
    """Look up a provider by name, falling back to the configured default."""
    name = (name or default_provider()).lower()
    provider = PROVIDERS.get(name)
    if provider is None:
        raise ProviderError(f"Unknown provider {name!r}; choose from {', '.join(PROVIDERS)}")
    return provider


async def resolve_model(
    client: httpx.AsyncClient,
    provider: Provider,
    api_key: str,
    override: str | None = None,
) -> str:
    """Resolve a model, discovering the sole model on self-hosted servers."""
    name = provider.model(override)
    if name:
        return name

    url = f"{provider.base_url}/models"
    try:
        resp = await client.get(url, headers=_openai_headers(api_key), timeout=_TIMEOUT)
        resp.raise_for_status()
        served = [
            m["id"] for m in resp.json().get("data", []) if isinstance(m, dict) and m.get("id")
        ]
    except (httpx.HTTPError, ValueError, TypeError, AttributeError) as e:
        raise ProviderError(
            f"Could not ask {url} which model it serves ({type(e).__name__}); "
            f"set {provider.model_env} to name it explicitly"
        ) from e

    if not served:
        raise ProviderError(f"{url} lists no models; set {provider.model_env} to name one")
    if len(served) > 1:
        raise ProviderError(
            f"{url} serves {len(served)} models ({', '.join(served[:3])}); "
            f"set {provider.model_env} to choose one"
        )

    _discovered_models[provider.base_url] = served[0]
    return served[0]


def display_model(provider: Provider) -> str:
    """Return a display value without triggering model discovery."""
    return provider.model() or "auto"


def _require_key(provider: Provider, key: str | None = None) -> str:
    """Return an explicit or environment-provided API key."""
    if key:
        return key
    env_key = provider.api_key
    if env_key is None:
        raise ProviderError(f"{provider.key_env} is not set")
    return env_key


def provider_status() -> list[dict]:
    """Return provider metadata for single-user clients."""
    default = default_provider()
    return [
        {
            "name": p.name,
            "model": display_model(p),
            "available": p.api_key is not None,
            "default": p.name == default,
        }
        for p in PROVIDERS.values()
    ]


def provider_status_for(user_id: str) -> list[dict]:
    """Return provider metadata with per-user key availability."""
    default = default_provider()
    out: list[dict] = []
    for p in PROVIDERS.values():
        out.append(
            {
                "name": p.name,
                "model": display_model(p),
                "available": p.api_key is not None or _user_has_active_key(user_id, p.name),
                "default": p.name == default,
            }
        )
    return out


def _user_has_active_key(user_id: str, provider_name: str) -> bool:
    """Return whether the user has an active key for the provider."""
    try:
        from surgite.db import ProviderKeyRow, get_session
    except ImportError:
        return False
    with get_session() as s:
        row = s.scalar(
            select(ProviderKeyRow).where(
                ProviderKeyRow.user_id == user_id,
                ProviderKeyRow.provider == provider_name,
                ProviderKeyRow.revoked_at.is_(None),
            )
        )
        return row is not None


def user_provider_key(user_id: str, provider_name: str) -> str | None:
    """Decrypt the user's active provider key, if any."""
    try:
        from surgite.db import ProviderKeyRow, get_session
        from surgite.secrets import decrypt
    except ImportError:
        return None
    with get_session() as s:
        row = s.scalar(
            select(ProviderKeyRow).where(
                ProviderKeyRow.user_id == user_id,
                ProviderKeyRow.provider == provider_name,
                ProviderKeyRow.revoked_at.is_(None),
            )
        )
        if row is None:
            return None
        try:
            return decrypt(row.encrypted_key)
        except ValueError:
            return None


def _build_system_prompt(settings: dict | None = None) -> str:
    s = settings or {}
    user = s.get("user_name") or os.environ.get("SURGITE_USER", "")
    role = s.get("user_role") or os.environ.get("SURGITE_ROLE", "")
    who = f"{user} ({role})" if user and role else user or "the developer"
    attribution = f"All commits were authored by {who}." if who != "the developer" else ""

    tone = s.get("tone", "neutral")
    tone_instruction = _TONE_INSTRUCTIONS.get(tone, _TONE_INSTRUCTIONS["neutral"])

    group_count = s.get("group_count") or "2-5"
    output_format = s.get("output_format", "markdown")

    if output_format == "plain":
        format_instruction = (
            "Format the response as plain text: each group is a label on its own line "
            "followed by '- ' bullets, each describing a distinct piece of work."
        )
    else:
        format_instruction = (
            "Format the response as Markdown: each group is a '## <Theme>' heading followed by "
            "'- ' bullets, each describing a distinct piece of work."
        )

    prompt = (
        "You are a tool that summarizes git commit history into a concise standup update. "
        + (attribution + " " if attribution else "")
        + "Group the work into a few thematic sections by feature area or type of work "
        "(for example: a feature name, Bug fixes, Documentation, Infrastructure, Tests) "
        "instead of one long flat list. "
        + format_instruction
        + f" Use {group_count} groups; with only a little activity, a single group is fine. "
        + tone_instruction
        + " No preamble, intro line, filler, or sign-off — start directly with the first heading or label."
    )

    custom = s.get("custom_instructions", "")
    if custom:
        prompt += " " + custom

    return prompt


def _openai_body(model: str, system: str, user_text: str, *, stream: bool) -> dict:
    return {
        "model": model,
        "stream": stream,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_text},
        ],
    }


def _anthropic_body(model: str, system: str, user_text: str, *, stream: bool) -> dict:
    return {
        "model": model,
        "max_tokens": _MAX_TOKENS,
        "stream": stream,
        "system": system,
        "messages": [{"role": "user", "content": user_text}],
    }


def _openai_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def _anthropic_headers(api_key: str) -> dict[str, str]:
    return {"x-api-key": api_key, "anthropic-version": "2023-06-01"}


def _request(provider: Provider, api_key: str, model: str, system: str, user_text: str):
    """Return (url, headers, json_body) for a non-streaming call."""
    if provider.kind == "anthropic":
        return (
            f"{provider.base_url}/v1/messages",
            _anthropic_headers(api_key),
            _anthropic_body(model, system, user_text, stream=False),
        )
    return (
        f"{provider.base_url}/chat/completions",
        _openai_headers(api_key),
        _openai_body(model, system, user_text, stream=False),
    )


def _extract_text(provider: Provider, payload: dict) -> str:
    if provider.kind == "anthropic":
        blocks = payload.get("content", [])
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    else:
        text = payload["choices"][0]["message"]["content"] or ""
    return text or "No summary available."


def _delta_text(payload: dict) -> str | None:
    """Extract text from an OpenAI or Anthropic stream event."""
    if "choices" in payload:
        return payload["choices"][0].get("delta", {}).get("content") or None
    if payload.get("type") == "content_block_delta":
        return payload.get("delta", {}).get("text") or None
    return None


async def _post_json(
    client: httpx.AsyncClient,
    provider: Provider,
    api_key: str,
    model: str,
    system: str,
    user_text: str,
) -> str:
    url, headers, body = _request(provider, api_key, model, system, user_text)
    resp = await client.post(url, headers=headers, json=body, timeout=_TIMEOUT)
    resp.raise_for_status()
    return _extract_text(provider, resp.json())


def _resolve_key(resolved: Provider, user_id: str | None) -> str:
    """Prefer the user's provider key, falling back to the environment."""
    if user_id is not None:
        per_user = user_provider_key(user_id, resolved.name)
        if per_user is not None:
            return per_user
    return _require_key(resolved)


async def generate_summary(
    commit_log: str,
    provider: str | None = None,
    model: str | None = None,
    settings: dict | None = None,
    client: httpx.AsyncClient | None = None,
    user_id: str | None = None,
    api_key: str | None = None,
) -> dict:
    """Summarize a commit log and return the text, provider, and model."""
    resolved = resolve_provider(provider)
    api_key = api_key or _resolve_key(resolved, user_id)
    system = _build_system_prompt(settings)

    async def run(c: httpx.AsyncClient) -> dict:
        chosen_model = await resolve_model(c, resolved, api_key, model)
        summary = await _post_json(c, resolved, api_key, chosen_model, system, commit_log)
        return {"summary": summary, "provider": resolved.name, "model": chosen_model}

    if client is not None:
        return await run(client)
    async with httpx.AsyncClient() as owned:
        return await run(owned)


async def generate_summary_per_repo(
    log_by_repo: dict[str, str],
    provider: str | None = None,
    settings: dict | None = None,
    settings_by_repo: dict[str, dict] | None = None,
    user_id: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> dict[str, dict[str, str]]:
    """Summarize repos concurrently with bounded provider calls."""
    pending = {name: log for name, log in log_by_repo.items() if log.strip()}
    by_repo = settings_by_repo or {}
    summaries: dict[str, dict[str, str]] = {}

    if pending:
        sem = asyncio.Semaphore(_MAX_PARALLEL_SUMMARIES)
        chosen_model: str | None = None

        def failure(exc: ProviderError | httpx.HTTPError) -> dict[str, str]:
            prefix = "Error" if isinstance(exc, ProviderError) else "Provider request failed"
            return {"summary": f"{prefix}: {exc}", "provider": "", "model": ""}

        async def summarize(client: httpx.AsyncClient, name: str, log_text: str) -> dict[str, str]:
            async with sem:
                try:
                    if chosen_model is None and api_key is None:
                        return await generate_summary(
                            log_text,
                            provider=provider,
                            settings=by_repo.get(name, settings),
                            client=client,
                            user_id=user_id,
                        )
                    return await generate_summary(
                        log_text,
                        provider=provider,
                        model=chosen_model,
                        settings=by_repo.get(name, settings),
                        client=client,
                        user_id=user_id,
                        api_key=api_key,
                    )
                except (ProviderError, httpx.HTTPError) as exc:
                    return failure(exc)

        async with httpx.AsyncClient() as client:
            try:
                if api_key is not None or model is not None:
                    resolved = resolve_provider(provider)
                    resolved_key = api_key or _resolve_key(resolved, user_id)
                    chosen_model = model or await resolve_model(client, resolved, resolved_key)
            except ProviderError as exc:
                results = [failure(exc) for _ in pending]
            else:
                results = await asyncio.gather(
                    *(summarize(client, name, log) for name, log in pending.items())
                )
        summaries = dict(zip(pending, results, strict=True))

    empty = {"summary": "No commits in this period.", "provider": "", "model": ""}
    return {name: summaries.get(name, empty) for name in log_by_repo}


async def stream_summary(
    commit_log: str,
    provider: str | None = None,
    model: str | None = None,
    settings: dict | None = None,
    client: httpx.AsyncClient | None = None,
    user_id: str | None = None,
    api_key: str | None = None,
) -> AsyncIterator[str]:
    """Yield text deltas from a provider's streaming response."""
    resolved = resolve_provider(provider)
    api_key = api_key or _resolve_key(resolved, user_id)
    system = _build_system_prompt(settings)

    async def pump(c: httpx.AsyncClient) -> AsyncIterator[str]:
        chosen_model = await resolve_model(c, resolved, api_key, model)
        if resolved.kind == "anthropic":
            url = f"{resolved.base_url}/v1/messages"
            headers = _anthropic_headers(api_key)
            body = _anthropic_body(chosen_model, system, commit_log, stream=True)
        else:
            url = f"{resolved.base_url}/chat/completions"
            headers = _openai_headers(api_key)
            body = _openai_body(chosen_model, system, commit_log, stream=True)

        async with c.stream("POST", url, headers=headers, json=body, timeout=_TIMEOUT) as resp:
            if resp.status_code >= 400:
                await resp.aread()
                resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[len("data:") :].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    payload = json.loads(data)
                except json.JSONDecodeError:
                    continue
                text = _delta_text(payload)
                if text:
                    yield text

    if client is not None:
        async for chunk in pump(client):
            yield chunk
    else:
        async with httpx.AsyncClient() as owned:
            async for chunk in pump(owned):
                yield chunk


def summarize_commits(summary: str, provider: str | None = None) -> str:
    """Synchronously summarize commits for the CLI."""
    return asyncio.run(generate_summary(summary, provider=provider))["summary"]
