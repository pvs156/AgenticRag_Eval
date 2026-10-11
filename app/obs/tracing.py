"""Tracing facade over Langfuse (v4, OpenTelemetry-based).

- No Langfuse keys -> every call is a cheap no-op, so local dev, tests and CI need no account.
- PII is masked before anything leaves the process (Langfuse `mask` hook).
- Spans: one trace per chat turn; child spans per agent node; generations per LLM call.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any

from app.config import get_settings
from app.guardrails.pii import redact

log = logging.getLogger(__name__)


class _NoopObs:
    def update(self, **_: Any) -> None:
        pass

    def score(self, **_: Any) -> None:
        pass


def _mask(*, data: Any, **_: Any) -> Any:
    if isinstance(data, str):
        return redact(data).text
    if isinstance(data, dict):
        return {k: _mask(data=v) for k, v in data.items()}
    if isinstance(data, list):
        return [_mask(data=v) for v in data]
    return data


class Tracer:
    def __init__(self) -> None:
        s = get_settings()
        self.client = None
        if s.langfuse_public_key and s.langfuse_secret_key:
            try:
                from langfuse import Langfuse

                self.client = Langfuse(
                    public_key=s.langfuse_public_key,
                    secret_key=s.langfuse_secret_key,
                    host=s.langfuse_host,
                    mask=_mask,
                    environment=s.app_env,
                    release=s.app_release,
                )
            except Exception as err:  # tracing must never break the product
                log.warning("Langfuse disabled: %s", err)

    @property
    def enabled(self) -> bool:
        return self.client is not None

    @contextmanager
    def span(self, name: str, *, as_type: str = "span", input: Any = None, metadata: dict | None = None, **kw: Any):
        if not self.client:
            yield _NoopObs()
            return
        with self.client.start_as_current_observation(
            name=name, as_type=as_type, input=input, metadata=metadata, **kw
        ) as obs:
            yield obs

    def current_trace_id(self) -> str | None:
        return self.client.get_current_trace_id() if self.client else None

    def trace_url(self, trace_id: str | None) -> str | None:
        if not (self.client and trace_id):
            return None
        try:
            return self.client.get_trace_url(trace_id=trace_id)
        except Exception:
            return None

    def set_trace_io(self, *, input: Any = None, output: Any = None) -> None:
        if self.client:
            self.client.set_current_trace_io(input=input, output=output)

    def score(
        self,
        *,
        trace_id: str | None,
        name: str,
        value: float | str,
        comment: str | None = None,
        data_type: str | None = None,
    ) -> None:
        if self.client and trace_id:
            self.client.create_score(trace_id=trace_id, name=name, value=value, comment=comment, data_type=data_type)

    def flush(self) -> None:
        if self.client:
            self.client.flush()


_tracer: Tracer | None = None


def get_tracer() -> Tracer:
    global _tracer
    if _tracer is None:
        _tracer = Tracer()
    return _tracer
