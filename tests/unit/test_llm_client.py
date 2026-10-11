import json

import httpx
import pytest
from pydantic import BaseModel

from app.llm.client import LLM, BudgetExceeded, LLMError


class Out(BaseModel):
    ok: bool


def fake_llm(monkeypatch, replies: list[str], **kw) -> tuple[LLM, list[dict]]:
    calls: list[dict] = []

    def post(url, json, headers, timeout):  # noqa: A002 - mirrors httpx signature
        calls.append(json)
        content = replies[min(len(calls) - 1, len(replies) - 1)]
        body = {
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 1000, "completion_tokens": 100},
        }
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", post)
    return LLM(base_url="http://x/v1", api_key="k", model="m", **kw), calls


def test_structured_parses_fenced_json(monkeypatch):
    llm, _ = fake_llm(monkeypatch, ['```json\n{"ok": true}\n```'])
    assert llm.structured([{"role": "user", "content": "hi"}], Out).ok is True


def test_structured_repairs_once(monkeypatch):
    llm, calls = fake_llm(monkeypatch, ["not json", '{"ok": false}'])
    assert llm.structured([{"role": "user", "content": "hi"}], Out).ok is False
    assert len(calls) == 2


def test_structured_fails_closed_after_repair(monkeypatch):
    llm, _ = fake_llm(monkeypatch, ["nope", "still nope"])
    with pytest.raises(LLMError):
        llm.structured([{"role": "user", "content": "hi"}], Out)


def test_cost_tracking_and_budget(monkeypatch):
    llm, _ = fake_llm(monkeypatch, ['{"ok": true}'], price_in=1.0, price_out=10.0, budget_usd=0.0015)
    llm.chat([{"role": "user", "content": "a"}])
    assert llm.spent_usd == pytest.approx(0.002)  # 1000*1/1e6 + 100*10/1e6
    with pytest.raises(BudgetExceeded):
        llm.chat([{"role": "user", "content": "b"}])


def test_disk_cache_avoids_second_call(monkeypatch, tmp_path):
    llm, calls = fake_llm(monkeypatch, ['{"ok": true}'], cache_dir=str(tmp_path))
    msgs = [{"role": "user", "content": "same"}]
    assert llm.chat(msgs) == llm.chat(msgs)
    assert len(calls) == 1
    assert json.loads(next(tmp_path.iterdir()).read_text())["text"] == '{"ok": true}'


def test_think_tags_are_stripped(monkeypatch):
    llm, _ = fake_llm(monkeypatch, ["<think>internal</think>answer"])
    assert llm.chat([{"role": "user", "content": "q"}]) == "answer"


def test_retry_after_reads_gemini_retry_delay():
    from app.llm.client import _retry_after

    body = '[{"error": {"code": 429, "details": [{"retryDelay": "41s"}]}}]'
    assert _retry_after(httpx.Response(429, text=body)) == 42.0
    assert _retry_after(httpx.Response(429, headers={"retry-after": "7"})) == 7.0


def test_429_is_retried_then_succeeds(monkeypatch):
    calls = []

    def post(url, json, headers, timeout):  # noqa: A002
        calls.append(1)
        req = httpx.Request("POST", url)
        if len(calls) == 1:
            return httpx.Response(429, text='{"retryDelay": "0s"}', request=req)
        return httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}], "usage": {}}, request=req)

    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setattr("app.llm.client.time.sleep", lambda s: None)
    assert LLM(base_url="http://x/v1", api_key="k", model="m").chat([{"role": "user", "content": "q"}]) == "hi"
    assert len(calls) == 2


def test_daily_quota_fails_fast(monkeypatch):
    def post(url, json, headers, timeout):  # noqa: A002
        return httpx.Response(429, text='{"retryDelay": "69309s"}', request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", post)
    with pytest.raises(LLMError, match="quota exhausted"):
        LLM(base_url="http://x/v1", api_key="k", model="m").chat([{"role": "user", "content": "q"}])
