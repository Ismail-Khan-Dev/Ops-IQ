"""Tests for LLM tracing decorators.

Covers M9 (trace_llm_call must read token usage from the model response, not
just forward it from call kwargs) and the no-usage fallback path.
"""

from unittest.mock import MagicMock

import pytest

from ecommerce_ops.observability import tracing as tracing_mod
from ecommerce_ops.observability.tracing import trace_llm_call


def _fake_client() -> MagicMock:
    client = MagicMock()
    client.create_generation = MagicMock()
    return client


@pytest.mark.asyncio
async def test_trace_llm_call_extracts_usage_from_dict_response(monkeypatch):
    client = _fake_client()
    monkeypatch.setattr(tracing_mod, "langfuse_client", client)

    @trace_llm_call(model="gemini-2.0-flash", name="call")
    async def llm(prompt: str):
        return {
            "text": "ok",
            "usage": {"total_tokens": 12, "prompt_tokens": 5, "completion_tokens": 7},
        }

    result = await llm(prompt="hi", trace_id="trace-1")
    assert result["text"] == "ok"

    sent = client.create_generation.call_args.kwargs
    assert sent["usage"] == {"total_tokens": 12, "prompt_tokens": 5, "completion_tokens": 7}


@pytest.mark.asyncio
async def test_trace_llm_call_extracts_usage_from_object_response(monkeypatch):
    client = _fake_client()
    monkeypatch.setattr(tracing_mod, "langfuse_client", client)

    usage = {"total_tokens": 3, "prompt_tokens": 1, "completion_tokens": 2}
    response = MagicMock()
    response.usage = usage

    @trace_llm_call(model="gemini-2.0-flash", name="call")
    async def llm(prompt: str):
        return response

    await llm(prompt="hi", trace_id="trace-1")
    assert client.create_generation.call_args.kwargs["usage"] == usage


@pytest.mark.asyncio
async def test_trace_llm_call_usage_absent_when_not_present(monkeypatch):
    client = _fake_client()
    monkeypatch.setattr(tracing_mod, "langfuse_client", client)

    @trace_llm_call(model="gemini-2.0-flash", name="call")
    async def llm(prompt: str):
        return {"text": "ok"}

    result = await llm(prompt="hi", trace_id="trace-1")
    assert result == {"text": "ok"}
    # Generation was still emitted, just without usage data
    assert client.create_generation.call_args.kwargs["usage"] is None
