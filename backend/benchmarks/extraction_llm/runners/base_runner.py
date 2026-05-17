"""OpenAI-compatible HTTP runner with timing + retry.

Used by all single-turn benchmark suites. Multi-turn (T2 recall agent)
extends this in agent_replay_runner.py (Phase 4).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class CallResult:
    raw_output: str
    elapsed_s: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    finish_reason: str = "unknown"
    tokens_per_sec: float = 0.0
    error: str | None = None
    error_kind: str | None = None       # 'timeout' | 'http' | 'parse' | 'connection'
    raw_response_meta: dict[str, Any] = field(default_factory=dict)


def call_chat_completion(
    endpoint: str,
    messages: list[dict[str, str]],
    request_params: dict[str, Any] | None = None,
    timeout_s: float = 60.0,
    headers: dict[str, str] | None = None,
    inference_path: str = "/v1/chat/completions",
    model_label: str = "",
    thinking_disable: str | None = None,
) -> CallResult:
    """POST to a /v1/chat/completions endpoint with timing.

    Catches timeouts and connection errors so the orchestrator can mark
    fixtures as failed and continue. Never raises on LLM-side failures —
    that data goes into CallResult.error.

    thinking_disable controls model-specific reasoning/thinking suppression:
      - "enable_thinking_false" (or None with model_label match) — sends
        `chat_template_kwargs.enable_thinking=False` (works for Qwen3/3.5,
        GLM, Gemma 4).
      - "reasoning_effort_none" — sends `reasoning_effort="none"`
        (OpenAI-style models).
      - "thinking_budget_zero" — sends `thinking_config.thinking_budget=0`
        (Gemini-style models).
      - "none" or empty — no override.
    If thinking_disable is None, falls back to legacy label-substring
    detection (qwen/glm/gemma → enable_thinking_false) for backwards compat.
    """
    params = dict(request_params or {})
    payload = {
        "model": params.get("model", "extraction"),
        "messages": messages,
        "temperature": params.get("temperature", 0.3),
        "top_p": params.get("top_p", 0.95),
        "max_tokens": params.get("max_tokens", 2000),
        "stream": False,
    }
    if "min_p" in params:
        payload["min_p"] = params["min_p"]
    if "stop" in params:
        payload["stop"] = params["stop"]

    # Resolve thinking_disable mode: explicit config wins; otherwise fall back
    # to label-substring auto-detection. Mirrors what extraction_service.py
    # does via `thinking_disable_method` in production.
    mode = thinking_disable
    if mode is None:
        label = (model_label or "").lower()
        if "qwen" in label or "glm" in label or "gemma" in label:
            mode = "enable_thinking_false"
    if mode == "enable_thinking_false":
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    elif mode == "reasoning_effort_none":
        payload["reasoning_effort"] = "none"
    elif mode == "thinking_budget_zero":
        payload["thinking_config"] = {"thinking_budget": 0}
    # "none" or unrecognized → no override

    url = f"{endpoint.rstrip('/')}{inference_path}"
    start = time.time()
    try:
        resp = httpx.post(url, json=payload, timeout=timeout_s, headers=headers)
        elapsed = time.time() - start
    except httpx.TimeoutException as exc:
        return CallResult(
            raw_output="",
            elapsed_s=time.time() - start,
            error=str(exc),
            error_kind="timeout",
        )
    except httpx.ConnectError as exc:
        return CallResult(
            raw_output="",
            elapsed_s=time.time() - start,
            error=str(exc),
            error_kind="connection",
        )

    if resp.status_code >= 400:
        return CallResult(
            raw_output="",
            elapsed_s=elapsed,
            error=f"HTTP {resp.status_code}: {resp.text[:300]}",
            error_kind="http",
        )

    try:
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        return CallResult(
            raw_output=resp.text,
            elapsed_s=elapsed,
            error=f"response not valid JSON: {exc}",
            error_kind="parse",
        )

    choice = (data.get("choices") or [{}])[0]
    content = (choice.get("message") or {}).get("content", "") or ""
    finish = choice.get("finish_reason", "unknown")
    usage = data.get("usage") or {}
    completion_tokens = usage.get("completion_tokens", 0)
    tps = completion_tokens / elapsed if elapsed > 0 and completion_tokens else 0.0

    return CallResult(
        raw_output=content,
        elapsed_s=round(elapsed, 3),
        prompt_tokens=usage.get("prompt_tokens", 0),
        completion_tokens=completion_tokens,
        total_tokens=usage.get("total_tokens", 0),
        finish_reason=finish,
        tokens_per_sec=round(tps, 2),
        raw_response_meta={
            "id": data.get("id"),
            "model": data.get("model"),
        },
    )


def wait_for_endpoint(endpoint: str, timeout_s: float = 60.0, health_path: str = "/v1/models") -> bool:
    """Poll the endpoint until it responds. Returns True on success."""
    deadline = time.time() + timeout_s
    url = f"{endpoint.rstrip('/')}{health_path}"
    while time.time() < deadline:
        try:
            r = httpx.get(url, timeout=2.0)
            if r.status_code == 200:
                return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2)
    return False


def check_thinking_health(
    endpoint: str,
    model_label: str = "",
    thinking_disable: str | None = None,
    inference_path: str = "/v1/chat/completions",
) -> tuple[bool, str]:
    """Send a trivial 'reply OK' prompt and check for the thinking-mode bug.

    Returns (ok, message). Detects the failure mode where a model returns
    empty `content` despite non-zero `completion_tokens` (Qwen3.5/Gemma 4
    when thinking isn't disabled — every fixture would burn its budget on
    a hidden `<think>` block and the client sees empty output).

    Call before running a battery against any new model. If this fails, the
    `thinking_disable` setting for the model is likely wrong.
    """
    result = call_chat_completion(
        endpoint=endpoint,
        messages=[{"role": "user", "content": "reply OK"}],
        request_params={"temperature": 0.0, "max_tokens": 50},
        timeout_s=30.0,
        inference_path=inference_path,
        model_label=model_label,
        thinking_disable=thinking_disable,
    )
    if result.error:
        return False, f"call failed: {result.error_kind}: {result.error}"
    if result.completion_tokens > 0 and not result.raw_output.strip():
        return False, (
            f"model emitted {result.completion_tokens} tokens but content is empty — "
            "thinking-mode bug? Try thinking_disable=enable_thinking_false in config.yaml "
            "(or reasoning_effort_none / thinking_budget_zero depending on model family)."
        )
    if not result.raw_output.strip():
        return False, f"empty content + zero tokens (finish={result.finish_reason})"
    return True, f"ok ({result.completion_tokens} tokens, {result.elapsed_s}s)"
