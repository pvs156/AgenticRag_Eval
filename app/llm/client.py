"""Minimal OpenAI-compatible chat client.

Works with local Ollama, Groq, Gemini's OpenAI-compatible endpoint, OpenRouter, OpenAI, etc.; switching
provider is configuration only. Adds: structured output validated by Pydantic with one repair attempt,
retries with backoff, token and cost accounting, an optional spend cap, and an on-disk cache for evals.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.config import Settings, get_settings

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


class BudgetExceeded(LLMError):
    pass


@dataclass
class CallRecord:
    name: str
    model: str
    messages: list[dict]
    output: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_s: float
    cached: bool


@dataclass
class LLM:
    base_url: str
    api_key: str
    model: str
    timeout_s: float = 120.0
    reasoning_effort: str | None = None
    price_in: float = 0.0  # USD per million input tokens
    price_out: float = 0.0
    budget_usd: float | None = None
    cache_dir: str | None = None
    spent_usd: float = 0.0
    tier: str = "generator"  # generator | judge (metrics label)
    max_rpm: int = 0  # client-side pacing for rate-limited free tiers
    hooks: list[Callable[[CallRecord], None]] = field(default_factory=list)

    # ------------------------------------------------------------------ public API

    def chat(
        self,
        messages: list[dict],
        *,
        name: str = "llm",
        temperature: float = 0.0,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> str:
        if self.budget_usd is not None and self.spent_usd >= self.budget_usd:
            raise BudgetExceeded(f"spend cap ${self.budget_usd:.2f} reached")
        body: dict = {"model": self.model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if self.reasoning_effort:
            body["reasoning_effort"] = self.reasoning_effort

        key = self._cache_key(body)
        if (hit := self._cache_get(key)) is not None:
            self._emit(name, messages, hit, 0, 0, 0.0, 0.0, cached=True)
            return hit

        from app.obs import metrics
        from app.obs.tracing import get_tracer

        params = {"temperature": temperature, "max_tokens": max_tokens, "json_mode": json_mode}
        with get_tracer().span(
            name, as_type="generation", input=messages, model=self.model, model_parameters=params
        ) as gen:
            start = time.perf_counter()
            data = self._post(body)
            latency = time.perf_counter() - start
            text = data["choices"][0]["message"].get("content") or ""
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()  # some local models leak reasoning
            usage = data.get("usage") or {}
            tin, tout = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
            cost = (tin * self.price_in + tout * self.price_out) / 1e6
            gen.update(output=text, usage_details={"input": tin, "output": tout}, cost_details={"total": cost})
        self.spent_usd += cost
        metrics.LLM_TOKENS.labels(self.tier, "in").inc(tin)
        metrics.LLM_TOKENS.labels(self.tier, "out").inc(tout)
        metrics.LLM_COST.labels(self.tier).inc(cost)
        metrics.LLM_LATENCY.labels(self.tier).observe(latency)
        self._cache_put(key, text)
        self._emit(name, messages, text, tin, tout, cost, latency, cached=False)
        return text

    def structured(self, messages: list[dict], schema: type[T], *, name: str = "llm", max_tokens: int = 1024) -> T:
        """Ask for JSON matching `schema`; validate; one repair attempt; otherwise raise (callers fail closed)."""
        instruction = "Respond with a single JSON object only, no prose, matching this JSON schema:\n" + json.dumps(
            schema.model_json_schema()
        )
        msgs = [*messages, {"role": "system", "content": instruction}]
        raw = self.chat(msgs, name=name, json_mode=True, max_tokens=max_tokens)
        try:
            return schema.model_validate_json(_extract_json(raw))
        except (ValidationError, ValueError) as err:
            repair = [
                *msgs,
                {"role": "assistant", "content": raw},
                {"role": "user", "content": f"That was invalid: {str(err)[:500]}. Return corrected JSON only."},
            ]
            raw2 = self.chat(repair, name=f"{name}.repair", json_mode=True, max_tokens=max_tokens)
            try:
                return schema.model_validate_json(_extract_json(raw2))
            except (ValidationError, ValueError) as err2:
                raise LLMError(f"{name}: invalid structured output after repair: {err2}") from err2

    # ------------------------------------------------------------------ internals

    def _post(self, body: dict) -> dict:
        url = self.base_url.rstrip("/") + "/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        delay = 2.0
        attempts = 6
        for attempt in range(attempts):
            _pace(self.max_rpm)
            try:
                r = httpx.post(url, json=body, headers=headers, timeout=self.timeout_s)
                wait = _retry_after(r) if r.status_code == 429 else None
                if wait is not None and wait > 120:
                    # Daily quota exhausted: waiting hours helps no one. Fail fast so the agent falls back safely.
                    raise LLMError(f"LLM quota exhausted (retry in {wait / 3600:.1f} h): {r.text[:200]}")
                if r.status_code in (429, 500, 502, 503, 504) and attempt < attempts - 1:
                    time.sleep(min(wait or delay, 65))
                    delay = min(delay * 2, 60)
                    continue
                r.raise_for_status()
                return r.json()
            except (httpx.TimeoutException, httpx.TransportError) as err:
                if attempt == attempts - 1:
                    raise LLMError(f"LLM request failed: {err}") from err
                time.sleep(delay)
                delay *= 2
            except httpx.HTTPStatusError as err:
                raise LLMError(f"LLM HTTP {err.response.status_code}: {err.response.text[:300]}") from err
        raise LLMError("LLM request failed after retries")

    def _cache_key(self, body: dict) -> str:
        return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()

    def _cache_get(self, key: str) -> str | None:
        if not self.cache_dir:
            return None
        from pathlib import Path

        p = Path(self.cache_dir) / f"{key}.json"
        return json.loads(p.read_text(encoding="utf-8"))["text"] if p.exists() else None

    def _cache_put(self, key: str, text: str) -> None:
        if not self.cache_dir:
            return
        from pathlib import Path

        d = Path(self.cache_dir)
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{key}.json").write_text(json.dumps({"text": text}), encoding="utf-8")

    def _emit(self, name, messages, text, tin, tout, cost, latency, cached) -> None:
        rec = CallRecord(name, self.model, messages, text, tin, tout, cost, latency, cached)
        for hook in self.hooks:
            hook(rec)


_last_call = [0.0]
_pace_lock = __import__("threading").Lock()


def _pace(max_rpm: int) -> None:
    """Space calls evenly to stay under a provider's free-tier requests-per-minute limit (0 = no limit)."""
    if max_rpm <= 0:
        return
    with _pace_lock:
        wait = _last_call[0] + 60.0 / max_rpm - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.monotonic()


def _retry_after(r: httpx.Response) -> float | None:
    """Honour Retry-After, or Gemini's retryDelay ("41s") in the error body."""
    if h := r.headers.get("retry-after"):
        try:
            return float(h)
        except ValueError:
            pass
    m = re.search(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"', r.text)
    return float(m.group(1)) + 1 if m else None


def _extract_json(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found")
    return raw[start : end + 1]


def make_generator(s: Settings | None = None) -> LLM:
    s = s or get_settings()
    return LLM(
        base_url=s.llm_base_url,
        api_key=s.llm_api_key,
        model=s.llm_model,
        timeout_s=s.llm_timeout_s,
        reasoning_effort=s.llm_reasoning_effort,
        price_in=s.llm_price_per_mtok_in,
        price_out=s.llm_price_per_mtok_out,
        cache_dir=str(s.cache_dir / "llm") if s.llm_cache else None,
        max_rpm=s.llm_max_rpm,
    )


def make_judge(s: Settings | None = None) -> LLM:
    s = s or get_settings()
    return LLM(
        base_url=s.judge_base_url or s.llm_base_url,
        api_key=s.judge_api_key or s.llm_api_key,
        model=s.judge_model or s.llm_model,
        timeout_s=s.llm_timeout_s,
        reasoning_effort=s.llm_reasoning_effort if not s.judge_base_url else None,
        price_in=s.judge_price_per_mtok_in,
        price_out=s.judge_price_per_mtok_out,
        budget_usd=s.judge_budget_usd,
        tier="judge",
        cache_dir=str(s.cache_dir / "llm_judge"),
        max_rpm=s.llm_max_rpm,
    )
