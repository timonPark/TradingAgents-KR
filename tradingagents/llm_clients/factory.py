
from typing import Any

from .base_client import BaseLLMClient


def create_llm_client(
    provider: str,
    model: str,
    base_url: str | None = None,
    **kwargs,
) -> BaseLLMClient:
    """Create an LLM client for the specified provider.

    Provider modules are imported lazily so that simply importing this
    factory (e.g. during test collection) does not pull in heavy LLM SDKs
    or fail when their API keys are absent.

    Args:
        provider: LLM provider name
        model: Model name/identifier
        base_url: Optional base URL for API endpoint
        **kwargs: Additional provider-specific arguments

    Returns:
        Configured BaseLLMClient instance

    Raises:
        ValueError: If provider is not supported
    """
    provider_lower = provider.lower()

    # Claude Code 헤드리스 어댑터 (Task 1f #7 / 1g #8 — 하드 포크의 기본 백엔드).
    # Task 1g (#8) 가 이 분기의 정식 소유자이지만, Task 1f 가 default_config
    # 를 claude-code 로 이전시키므로 main 이 깨지지 않도록 여기서 함께 추가.
    if provider_lower == "claude-code":
        from .claude_code_client import ClaudeCodeClient
        return ClaudeCodeClient(model, base_url, **kwargs)

    # Native (non-OpenAI) APIs are matched first so their string check doesn't
    # import the OpenAI client. Everything else is OpenAI-compatible and routes
    # through the provider registry (single source of truth).
    if provider_lower == "anthropic":
        from .anthropic_client import AnthropicClient
        return AnthropicClient(model, base_url, **kwargs)

    if provider_lower == "google":
        from .google_client import GoogleClient
        return GoogleClient(model, base_url, **kwargs)

    if provider_lower == "azure":
        from .azure_client import AzureOpenAIClient
        return AzureOpenAIClient(model, base_url, **kwargs)

    if provider_lower == "bedrock":
        from .bedrock_client import BedrockClient
        return BedrockClient(model, base_url, **kwargs)

    from .openai_client import OpenAIClient, is_openai_compatible
    if is_openai_compatible(provider_lower):
        return OpenAIClient(model, base_url, provider=provider_lower, **kwargs)

    raise ValueError(f"Unsupported LLM provider: {provider}")


def _coerce_max_retries(value):
    """Validate an ``llm_max_retries`` value to a non-negative int.

    Accepts an int or a numeric string (env vars arrive as strings). Rejects
    booleans and negatives loudly so a misconfiguration fails at startup rather
    than silently disabling retries.
    """
    if isinstance(value, bool):
        raise ValueError(f"llm_max_retries must be an integer, not a boolean: {value!r}")
    try:
        n = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"llm_max_retries must be an integer, got {value!r}") from exc
    if n < 0:
        raise ValueError(f"llm_max_retries must be >= 0, got {n}")
    return n


def _coerce_max_tokens(value):
    """Validate a ``max_tokens`` value to a positive int (env vars are strings)."""
    if isinstance(value, bool):
        raise ValueError(f"max_tokens must be an integer, not a boolean: {value!r}")
    try:
        n = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"max_tokens must be an integer, got {value!r}") from exc
    if n <= 0:
        raise ValueError(f"max_tokens must be > 0, got {n}")
    return n


# Providers that take OpenAI's ``openai_reasoning_effort``.
REASONING_EFFORT_PROVIDERS = ("openai", "chatgpt")


def build_llm_kwargs(config: dict) -> dict[str, Any]:
    """Keyword arguments for ``create_llm_client`` from a TradingAgents config."""
    kwargs = {}
    provider = config.get("llm_provider", "").lower()

    if provider == "google":
        thinking_level = config.get("google_thinking_level")
        if thinking_level:
            kwargs["thinking_level"] = thinking_level

    elif provider in REASONING_EFFORT_PROVIDERS:
        reasoning_effort = config.get("openai_reasoning_effort")
        if reasoning_effort:
            kwargs["reasoning_effort"] = reasoning_effort

    elif provider == "anthropic":
        effort = config.get("anthropic_effort")
        if effort:
            kwargs["effort"] = effort

    elif provider == "claude-code":
        # `effort` 는 호출 티어에 맞게 `create_tier_client` 가 선조정해둠 —
        # build_llm_kwargs 는 tier-agnostic 하게 하나의 키만 본다.
        effort = config.get("effort")
        if effort:
            kwargs["effort"] = effort

    # Sampling temperature is cross-provider: forward it whenever set.
    # float() here so a value coming from a TRADINGAGENTS_TEMPERATURE env
    # string ("0.2") works the same as a programmatic float.
    temperature = config.get("temperature")
    if temperature is not None and temperature != "":
        kwargs["temperature"] = float(temperature)

    # SDK retry budget is cross-provider. Forward it only when explicitly set
    # so each provider keeps its own default (usually 2) otherwise (#1091).
    max_retries = config.get("llm_max_retries")
    if max_retries is not None and max_retries != "":
        kwargs["max_retries"] = _coerce_max_retries(max_retries)

    # Output-token cap is cross-provider, but Gemini names it
    # ``max_output_tokens``; forward under the right key when set (#1204).
    max_tokens = config.get("max_tokens")
    if max_tokens is not None and max_tokens != "":
        key = "max_output_tokens" if provider == "google" else "max_tokens"
        kwargs[key] = _coerce_max_tokens(max_tokens)

    return kwargs


def tier_provider(config: dict, tier: str) -> str:
    """The provider of the ``quick`` or ``deep`` model tier: its own, else ``llm_provider``."""
    return (config.get(f"{tier}_think_provider") or config["llm_provider"]).lower()


def create_tier_client(config: dict, tier: str, **extra) -> BaseLLMClient:
    """The client for the ``quick`` or ``deep`` model tier (#1440).

    A tier on its own provider gets that provider's settings (thinking level,
    reasoning effort, the name of the output-token cap) and its own endpoint,
    else the provider's default: ``backend_url`` belongs to ``llm_provider``.

    For Claude Code (Task 1f #7): the deep tier uses `effort`, the quick tier
    uses `quick_effort`. Both are normalised to the `effort` key before being
    passed to `build_llm_kwargs`, which is tier-agnostic.
    """
    provider = tier_provider(config, tier)
    if provider == config["llm_provider"].lower():
        base_url = config.get(f"{tier}_think_backend_url") or config.get("backend_url")
    else:
        base_url = config.get(f"{tier}_think_backend_url")
    tier_config = {**config, "llm_provider": provider}
    if provider == "claude-code":
        effort_key = "quick_effort" if tier == "quick" else "effort"
        tier_effort = config.get(effort_key)
        if tier_effort:
            tier_config["effort"] = tier_effort
    kwargs = build_llm_kwargs(tier_config)
    return create_llm_client(provider=provider, model=config[f"{tier}_think_llm"], base_url=base_url,
                             **kwargs, **extra)
