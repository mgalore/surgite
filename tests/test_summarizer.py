import json

import httpx
import pytest

from surgite import summarizer
from surgite.summarizer import (
    ProviderError,
    default_provider,
    generate_summary,
    generate_summary_per_repo,
    provider_status,
    resolve_provider,
    stream_summary,
    summarize_commits,
)


def _mock_client(handler) -> httpx.AsyncClient:
    """Build an HTTP client backed by a mock transport."""
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _anthropic_response(text: str) -> httpx.Response:
    return httpx.Response(200, json={"content": [{"type": "text", "text": text}]})


def _openai_response(text: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": text}}]})


@pytest.fixture(autouse=True)
def _clear_discovered_models():
    summarizer._discovered_models.clear()
    yield
    summarizer._discovered_models.clear()


# --- provider resolution ----------------------------------------------------


def test_default_provider_is_anthropic(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert default_provider() == "anthropic"


def test_default_provider_respects_env_case_insensitively(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "GROQ")
    assert default_provider() == "groq"


def test_resolve_provider_falls_back_to_default(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert resolve_provider(None).name == "anthropic"


def test_resolve_provider_explicit():
    assert resolve_provider("deepseek").name == "deepseek"


def test_resolve_provider_unknown_raises():
    with pytest.raises(ProviderError):
        resolve_provider("bogus")


# --- LLM_LOCAL_ONLY ---------------------------------------------------------


def test_local_only_leaves_just_the_self_hosted_provider(monkeypatch):
    monkeypatch.setenv("LLM_LOCAL_ONLY", "1")
    assert set(summarizer._visible(summarizer._ALL_PROVIDERS)) == {"local"}


def test_registry_is_unfiltered_without_the_flag(monkeypatch):
    monkeypatch.setenv("LLM_LOCAL_ONLY", "")
    visible = summarizer._visible(summarizer._ALL_PROVIDERS)
    assert set(visible) == {"groq", "deepseek", "anthropic", "local"}


def test_default_provider_falls_back_when_the_default_is_filtered_out(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setattr(summarizer, "PROVIDERS", {"local": summarizer._ALL_PROVIDERS["local"]})
    assert default_provider() == "local"


# --- provider_status --------------------------------------------------------


def test_provider_status_all_unavailable_without_keys():
    assert all(s["available"] is False for s in provider_status())


def test_provider_status_marks_configured_key_available(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    by_name = {s["name"]: s for s in provider_status()}
    assert by_name["groq"]["available"] is True
    assert by_name["deepseek"]["available"] is False


def test_provider_status_flags_the_default(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    by_name = {s["name"]: s for s in provider_status()}
    assert by_name["deepseek"]["default"] is True
    assert by_name["anthropic"]["default"] is False


# --- system prompt ----------------------------------------------------------


def test_system_prompt_includes_identity(monkeypatch):
    monkeypatch.setenv("SURGITE_USER", "Nick")
    monkeypatch.setenv("SURGITE_ROLE", "developer")
    assert "Nick (developer)" in summarizer._build_system_prompt()


def test_system_prompt_without_identity_has_no_attribution(monkeypatch):
    monkeypatch.delenv("SURGITE_USER", raising=False)
    monkeypatch.delenv("SURGITE_ROLE", raising=False)
    assert "authored by" not in summarizer._build_system_prompt()


def test_system_prompt_instructs_theme_grouping():
    prompt = summarizer._build_system_prompt()
    assert "## " in prompt
    assert "group" in prompt.lower()


def test_system_prompt_with_settings_identity():
    prompt = summarizer._build_system_prompt(
        {"user_name": "Alice", "user_role": "backend engineer"}
    )
    assert "Alice (backend engineer)" in prompt


def test_system_prompt_with_settings_first_person():
    prompt = summarizer._build_system_prompt({"tone": "first-person"})
    assert "first person" in prompt.lower()


def test_system_prompt_with_settings_plain_format():
    prompt = summarizer._build_system_prompt({"output_format": "plain"})
    assert "plain text" in prompt.lower()
    assert "## " not in prompt


def test_system_prompt_with_settings_custom_group_count():
    prompt = summarizer._build_system_prompt({"group_count": "1-3"})
    assert "1-3" in prompt


def test_system_prompt_with_custom_instructions():
    prompt = summarizer._build_system_prompt({"custom_instructions": "Focus on bug fixes."})
    assert "Focus on bug fixes." in prompt


def test_system_prompt_settings_override_env(monkeypatch):
    monkeypatch.setenv("SURGITE_USER", "EnvUser")
    prompt = summarizer._build_system_prompt({"user_name": "SettingsUser"})
    assert "SettingsUser" in prompt
    assert "EnvUser" not in prompt


def test_system_prompt_settings_fallback_to_env(monkeypatch):
    monkeypatch.setenv("SURGITE_USER", "EnvUser")
    monkeypatch.setenv("SURGITE_ROLE", "dev")
    prompt = summarizer._build_system_prompt({})
    assert "EnvUser (dev)" in prompt


# --- generate_summary (async, httpx) ----------------------------------------


async def test_generate_summary_missing_key_raises():
    # conftest leaves ANTHROPIC_API_KEY empty.
    with pytest.raises(ProviderError):
        await generate_summary("log", provider="anthropic")


async def test_generate_summary_anthropic_path(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    client = _mock_client(lambda req: _anthropic_response("Accomplishments:\n- shipped"))
    out = await generate_summary("commit log", provider="anthropic", client=client)
    assert out == {
        "summary": "Accomplishments:\n- shipped",
        "provider": "anthropic",
        "model": "claude-haiku-4-5-20251001",
    }


async def test_generate_summary_anthropic_request_shape(monkeypatch):
    """The Anthropic path must hit /v1/messages with the x-api-key header."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        seen["key"] = req.headers.get("x-api-key")
        return _anthropic_response("ok")

    await generate_summary("log", provider="anthropic", client=_mock_client(handler))
    assert seen["url"].endswith("/v1/messages")
    assert seen["key"] == "sk-ant-test"


async def test_generate_summary_openai_path_with_model_override(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    client = _mock_client(lambda req: _openai_response("Accomplishments:\n- did it"))
    out = await generate_summary("log", provider="groq", model="custom-model", client=client)
    assert out["summary"] == "Accomplishments:\n- did it"
    assert out["provider"] == "groq"
    assert out["model"] == "custom-model"


async def test_local_provider_uses_the_base_url_override(monkeypatch):
    monkeypatch.setenv("LOCAL_API_KEY", "internal-token")
    monkeypatch.setenv("LOCAL_BASE_URL", "http://llm.internal:8000/v1")
    monkeypatch.setenv("LOCAL_MODEL", "internal-model")
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        seen["auth"] = req.headers.get("Authorization")
        return _openai_response("ok")

    out = await generate_summary("log", provider="local", client=_mock_client(handler))
    assert seen["url"] == "http://llm.internal:8000/v1/chat/completions"
    assert seen["auth"] == "Bearer internal-token"
    assert out["provider"] == "local"
    assert out["model"] == "internal-model"


async def test_generate_summary_propagates_request_errors(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    def boom(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(httpx.HTTPError):
        await generate_summary("log", provider="anthropic", client=_mock_client(boom))


async def test_generate_summary_raises_on_http_error_status(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    client = _mock_client(lambda req: httpx.Response(500, json={"error": "boom"}))
    with pytest.raises(httpx.HTTPStatusError):
        await generate_summary("log", provider="groq", client=client)


def test_summarize_commits_returns_text_only(monkeypatch):
    """The CLI helper is sync; it drives the async path on its own loop."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")

    async def fake_generate(*a, **k):
        return {"summary": "just text", "provider": "deepseek", "model": "x"}

    monkeypatch.setattr(summarizer, "generate_summary", fake_generate)
    assert summarize_commits("log", provider="deepseek") == "just text"


# --- generate_summary_per_repo ----------------------------------------------


async def test_per_repo_blank_log_skips_provider():
    out = await generate_summary_per_repo({"repo-a": "   "})
    assert out["repo-a"]["summary"] == "No commits in this period."


async def test_per_repo_provider_error_is_captured_not_raised():
    # No key configured -> ProviderError captured per repo.
    out = await generate_summary_per_repo({"repo-a": "some log"}, provider="anthropic")
    assert out["repo-a"]["summary"].startswith("Error:")


async def test_per_repo_shared_model_discovery_error_is_captured_once(monkeypatch):
    calls = 0

    async def fail_discovery(*args):
        nonlocal calls
        calls += 1
        raise ProviderError("choose a local model")

    monkeypatch.setattr(summarizer, "resolve_model", fail_discovery)
    out = await generate_summary_per_repo(
        {"repo-a": "log-a", "repo-b": "log-b"},
        provider="local",
        api_key="local-test-key",
    )

    assert calls == 1
    assert [result["summary"] for result in out.values()] == [
        "Error: choose a local model",
        "Error: choose a local model",
    ]


async def test_per_repo_success(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")

    async def fake_generate(log_text, **kwargs):
        return {"summary": "## Features\n- x", "provider": "groq", "model": "m"}

    monkeypatch.setattr(summarizer, "generate_summary", fake_generate)
    out = await generate_summary_per_repo({"repo-a": "log"}, provider="groq")
    assert out["repo-a"]["summary"].startswith("## Features")
    assert out["repo-a"]["provider"] == "groq"


async def test_per_repo_uses_per_repo_settings(monkeypatch):
    """settings_by_repo overrides the fallback `settings` per repo."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    seen: dict[str, dict | None] = {}

    async def fake_generate(log_text, provider=None, settings=None, client=None, user_id=None):
        seen[log_text] = settings
        return {"summary": "ok", "provider": "groq", "model": "m"}

    monkeypatch.setattr(summarizer, "generate_summary", fake_generate)
    await generate_summary_per_repo(
        {"a": "log-a", "b": "log-b"},
        provider="groq",
        settings={"tone": "neutral"},
        settings_by_repo={"a": {"tone": "casual"}},
    )
    assert seen["log-a"] == {"tone": "casual"}
    assert seen["log-b"] == {"tone": "neutral"}


async def test_per_repo_preserves_input_order(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")

    async def fake_generate(log_text, **kwargs):
        return {"summary": "ok", "provider": "groq", "model": "m"}

    monkeypatch.setattr(summarizer, "generate_summary", fake_generate)
    out = await generate_summary_per_repo(
        {"zeta": "log", "blank": "  ", "alpha": "log"}, provider="groq"
    )
    assert list(out.keys()) == ["zeta", "blank", "alpha"]
    assert out["blank"]["summary"] == "No commits in this period."


# --- stream_summary ---------------------------------------------------------


async def test_stream_summary_openai_yields_deltas(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    sse = (
        b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n'
        b'data: {"choices":[{"delta":{"content":" world"}}]}\n\n'
        b"data: [DONE]\n\n"
    )
    client = _mock_client(lambda req: httpx.Response(200, content=sse))
    chunks = [c async for c in stream_summary("log", provider="groq", client=client)]
    assert "".join(chunks) == "Hello world"


async def test_stream_summary_anthropic_yields_deltas(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    sse = (
        b"event: content_block_delta\n"
        b'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Hi "}}\n\n'
        b"event: content_block_delta\n"
        b'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"there"}}\n\n'
        b"event: message_stop\ndata: {}\n\n"
    )
    client = _mock_client(lambda req: httpx.Response(200, content=sse))
    chunks = [c async for c in stream_summary("log", provider="anthropic", client=client)]
    assert "".join(chunks) == "Hi there"


async def test_stream_summary_missing_key_raises():
    with pytest.raises(ProviderError):
        async for _ in stream_summary("log", provider="anthropic"):
            pass


async def test_stream_summary_raises_on_http_error_status(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    client = _mock_client(lambda req: httpx.Response(429, json={"error": "rate"}))
    with pytest.raises(httpx.HTTPStatusError):
        async for _ in stream_summary("log", provider="groq", client=client):
            pass


# --- self-hosted model discovery --------------------------------------------


def _models_response(*ids: str) -> httpx.Response:
    return httpx.Response(200, json={"data": [{"id": i} for i in ids]})


def _local_env(monkeypatch, model: str | None = None):
    monkeypatch.setenv("LOCAL_API_KEY", "internal-token")
    monkeypatch.setenv("LOCAL_BASE_URL", "http://llm.internal:8000/v1")
    if model is None:
        monkeypatch.delenv("LOCAL_MODEL", raising=False)
    else:
        monkeypatch.setenv("LOCAL_MODEL", model)


async def test_local_model_is_discovered_when_unset(monkeypatch):
    _local_env(monkeypatch)
    seen: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(str(req.url))
        if req.url.path.endswith("/models"):
            assert req.headers.get("Authorization") == "Bearer internal-token"
            return _models_response("Qwen/Qwen3.6-32B")
        assert json.loads(req.content)["model"] == "Qwen/Qwen3.6-32B"
        return _openai_response("ok")

    out = await generate_summary("log", provider="local", client=_mock_client(handler))
    assert out["model"] == "Qwen/Qwen3.6-32B"
    assert seen[0].endswith("/v1/models")


async def test_discovered_model_is_cached_across_calls(monkeypatch):
    _local_env(monkeypatch)
    probes = 0

    def handler(req: httpx.Request) -> httpx.Response:
        nonlocal probes
        if req.url.path.endswith("/models"):
            probes += 1
            return _models_response("some-model")
        return _openai_response("ok")

    client = _mock_client(handler)
    await generate_summary("log", provider="local", client=client)
    await generate_summary("log again", provider="local", client=client)
    assert probes == 1, "should ask the server once, then reuse the answer"


async def test_explicit_local_model_skips_discovery(monkeypatch):
    _local_env(monkeypatch, model="my-model")

    def handler(req: httpx.Request) -> httpx.Response:
        assert not req.url.path.endswith("/models"), "should not probe when configured"
        return _openai_response("ok")

    out = await generate_summary("log", provider="local", client=_mock_client(handler))
    assert out["model"] == "my-model"


async def test_ambiguous_model_list_asks_for_an_explicit_choice(monkeypatch):
    _local_env(monkeypatch)
    client = _mock_client(lambda req: _models_response("model-a", "model-b"))
    with pytest.raises(ProviderError, match="LOCAL_MODEL"):
        await generate_summary("log", provider="local", client=client)


async def test_empty_model_list_raises(monkeypatch):
    _local_env(monkeypatch)
    client = _mock_client(lambda req: _models_response())
    with pytest.raises(ProviderError, match="LOCAL_MODEL"):
        await generate_summary("log", provider="local", client=client)


async def test_unreachable_models_endpoint_names_the_env_var(monkeypatch):
    _local_env(monkeypatch)

    def boom(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(ProviderError, match="LOCAL_MODEL"):
        await generate_summary("log", provider="local", client=_mock_client(boom))


async def test_streaming_discovers_the_model_too(monkeypatch):
    _local_env(monkeypatch)

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/models"):
            return _models_response("streamed-model")
        assert json.loads(req.content)["model"] == "streamed-model"
        body = 'data: {"choices":[{"delta":{"content":"hi"}}]}\n\ndata: [DONE]\n\n'
        return httpx.Response(200, text=body)

    chunks = [
        c async for c in stream_summary("log", provider="local", client=_mock_client(handler))
    ]
    assert chunks == ["hi"]


def test_display_model_is_auto_until_discovery(monkeypatch):
    """The provider dropdown would otherwise render "local ()"."""
    _local_env(monkeypatch)
    local = summarizer._ALL_PROVIDERS["local"]
    assert summarizer.display_model(local) == "auto"
    summarizer._discovered_models[local.base_url] = "found-model"
    assert summarizer.display_model(local) == "found-model"
