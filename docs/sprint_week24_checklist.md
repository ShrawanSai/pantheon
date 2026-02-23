# Pantheon MVP - Sprint Week 24 Checklist

Sprint window: Week 24 (Cycle 8 Part 2 - Observability)
Owner: Codex
Reviewer: External supervising engineer
Last updated: 2026-02-23

## Sprint Goal
Add production-grade observability: request trace IDs on every response, structured logging with trace ID binding, Sentry error tracking (conditional on DSN), and LLM gateway latency instrumentation. OpenTelemetry SDK deferred — not in scope this week.

## Baseline
- Local tests at sprint open: `210` passing.
- Migration head at sprint open: `20260223_0018` (local).
- Open carry-forwards: F58 (Low), F62 (Low), F64 (Low), F70 (Medium, deployment-only).

## Definition of Done
- Every HTTP response carries an `X-Trace-ID` header (generated UUID or echoed from request).
- `current_trace_id` context var populated per request; key log lines include trace ID.
- Sentry initialized when `SENTRY_DSN` is set; no-op (and no import error) when unset.
- LLM gateway logs include `model_alias`, `latency_ms`, `input_tokens`, `output_tokens` per call.
- Existing 210 tests pass unchanged.
- 5 new observability tests pass.
- Total: `215/215`.
- Ruff critical (`E9,F63,F7,F82`): passing.
- No new migrations.
- Week 24 handoff published.

---

## Week 24 Task Checklist

| ID | Task | Status | Acceptance Criteria | Evidence / Notes |
|---|---|---|---|---|
| W24-01 | Config: Sentry settings | TODO | `sentry_dsn` and `sentry_traces_sample_rate` added | See spec below |
| W24-02 | `sentry-sdk[fastapi]` dependency | TODO | Added to `requirements.txt` | See spec below |
| W24-03 | Trace ID middleware | TODO | Pure ASGI middleware; `X-Trace-ID` on all responses including streaming | See spec below |
| W24-04 | Structured logging with trace ID | TODO | `configure_logging()` sets up filter + formatter; trace ID in log output | See spec below |
| W24-05 | Sentry init in lifespan | TODO | `sentry_sdk.init()` called with correct args when DSN is set; no-op when unset | See spec below |
| W24-06 | LLM gateway latency logging | TODO | `generate()` and `stream()` log `latency_ms`, `model_alias`, token counts | See spec below |
| W24-07 | Tests | TODO | 5 new tests pass; all 210 existing tests pass | See spec below |
| W24-08 | Docs | TODO | This checklist updated; `docs/sprint_week24_handoff.md` published | — |

---

## Task Specifications

### W24-01 — Config: Sentry settings

**File:** `apps/api/app/core/config.py`

Add to `Settings` dataclass:
```python
sentry_dsn: str | None          # env SENTRY_DSN; None = Sentry disabled
sentry_traces_sample_rate: float  # env SENTRY_TRACES_SAMPLE_RATE; default 0.1
```

Add to `get_settings()` return:
```python
sentry_dsn=os.getenv("SENTRY_DSN") or None,
sentry_traces_sample_rate=_float_env("SENTRY_TRACES_SAMPLE_RATE", 0.1),
```

---

### W24-02 — sentry-sdk dependency

**File:** `requirements.txt`

Add:
```
sentry-sdk[fastapi]>=2.0.0
```

The `[fastapi]` extra includes both `StarletteIntegration` and `FastApiIntegration`. Import is lazy (inside the `if settings.sentry_dsn:` block in lifespan), so the package can be installed without being initialized in test environments.

---

### W24-03 — Trace ID middleware

**File:** `apps/api/app/middleware/trace_id.py` (new)

Use a **pure ASGI middleware** (not `BaseHTTPMiddleware`) to avoid response buffering on streaming endpoints.

```python
from __future__ import annotations

import uuid
from contextvars import ContextVar

current_trace_id: ContextVar[str] = ContextVar("current_trace_id", default="")


class TraceIdMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        incoming = headers.get(b"x-trace-id", b"").decode().strip()
        trace_id = incoming if incoming else str(uuid.uuid4())
        token = current_trace_id.set(trace_id)

        async def send_with_trace_id(message: dict) -> None:
            if message["type"] == "http.response.start":
                existing = list(message.get("headers", []))
                existing.append((b"x-trace-id", trace_id.encode()))
                message = {**message, "headers": existing}
            await send(message)

        try:
            await self.app(scope, receive, send_with_trace_id)
        finally:
            current_trace_id.reset(token)
```

**Register in `main.py`** — add `app.add_middleware(TraceIdMiddleware)` **after** the CORS middleware call so the trace ID middleware is outermost (first to execute on requests, last to execute on responses).

```python
from apps.api.app.middleware.trace_id import TraceIdMiddleware
# in create_app(), after CORSMiddleware block:
app.add_middleware(TraceIdMiddleware)
```

---

### W24-04 — Structured logging with trace ID

**File:** `apps/api/app/core/logging_config.py` (new)

```python
from __future__ import annotations

import logging

from apps.api.app.middleware.trace_id import current_trace_id


class _TraceIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = current_trace_id.get("") or "-"
        return True


def configure_logging() -> None:
    fmt = "%(asctime)s %(levelname)-8s %(name)s [%(trace_id)s] %(message)s"
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(fmt))
    handler.addFilter(_TraceIdFilter())

    root = logging.getLogger()
    # Avoid double-adding if called multiple times (e.g., during testing)
    if not any(isinstance(h, logging.StreamHandler) and isinstance(h.formatter, logging.Formatter) for h in root.handlers):
        root.addHandler(handler)
    root.setLevel(logging.INFO)
    # Suppress noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
```

**Call `configure_logging()` in `main.py`** at module level, before `create_app()`:
```python
from apps.api.app.core.logging_config import configure_logging
configure_logging()
```

---

### W24-05 — Sentry init in lifespan

**File:** `apps/api/app/main.py` — `_lifespan()` function

Add Sentry initialization at the top of `_lifespan()`, before the Redis pool setup:

```python
@asynccontextmanager
async def _lifespan(app: FastAPI):
    settings = get_settings()
    if settings.sentry_dsn:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            traces_sample_rate=settings.sentry_traces_sample_rate,
            integrations=[StarletteIntegration(), FastApiIntegration()],
            send_default_pii=False,
        )
        _LOGGER.info("Sentry initialized (traces_sample_rate=%.2f)", settings.sentry_traces_sample_rate)
    # ... existing Redis pool setup ...
```

`sentry_sdk.init()` is idempotent and thread-safe. The lazy import (`import sentry_sdk` inside the `if` block) means `sentry-sdk` is never imported in environments where DSN is not configured, keeping test startup clean.

---

### W24-06 — LLM gateway latency logging

**File:** `apps/api/app/services/llm/gateway.py` — `OpenRouterLlmGateway` implementation only.

Add `time.perf_counter()` timing around both `generate()` and `stream()`. Log after each call:

In `generate()`:
```python
import time
t0 = time.perf_counter()
# ... existing generate call ...
latency_ms = int((time.perf_counter() - t0) * 1000)
_LOGGER.info(
    "llm.generate model=%s latency_ms=%d input_tokens=%d output_tokens=%d",
    request.model_alias,
    latency_ms,
    response.usage.input_tokens_fresh + response.usage.input_tokens_cached,
    response.usage.output_tokens,
)
```

In `stream()`: log after iterator exhaustion (i.e., after futures are resolved), not before — streaming latency = time to first token is less useful than total time. Log at the point where usage_future is resolved:
```python
# After: usage = await usage_future (or equivalent)
_LOGGER.info(
    "llm.stream model=%s latency_ms=%d input_tokens=%d output_tokens=%d",
    request.model_alias,
    int((time.perf_counter() - t0) * 1000),
    usage.input_tokens_fresh + usage.input_tokens_cached,
    usage.output_tokens,
)
```

The `trace_id` will appear automatically in the log line because `_TraceIdFilter` is attached to the root handler.

Do **not** add timing to the `LlmGateway` protocol definition — only to the concrete `OpenRouterLlmGateway` class.

---

### W24-07 — Tests

**File:** `tests/test_observability.py` (new)

Use the same test class setup pattern as existing test files (in-memory SQLite, `TestClient(app)`). Use the live `app` instance (no special gateway mocking needed — these tests hit lightweight routes like `/api/v1/health`).

**Required tests:**

| # | Name | What it verifies |
|---|---|---|
| 1 | `test_trace_id_generated_when_absent` | No `X-Trace-ID` header in request → UUID in response headers |
| 2 | `test_trace_id_propagated_when_present` | `X-Trace-ID: my-custom-id` in request → `x-trace-id: my-custom-id` in response |
| 3 | `test_trace_id_is_valid_uuid_when_generated` | Generated trace ID is parseable as `uuid.UUID` |
| 4 | `test_trace_id_present_on_error_response` | 404 response still carries `x-trace-id` header |
| 5 | `test_sentry_initialized_when_dsn_set` | Mock `sentry_sdk.init`; set `SENTRY_DSN` env; enter `TestClient` context (triggers lifespan); assert `sentry_sdk.init` called once with `dsn=` matching the set value |

**Notes on test 5:**
- Use `unittest.mock.patch("sentry_sdk.init")` as a context manager.
- Use `TestClient(app, raise_server_exceptions=False)` inside a `with` block to trigger lifespan.
- Clean up: `os.environ.pop("SENTRY_DSN")` + `get_settings.cache_clear()` in `addCleanup`.
- Do **not** assert `call_args` on integrations list (implementation detail); only assert `dsn` kwarg.

**Header case note:** `requests` (used by `TestClient`) lowercases all response header names. Assert `"x-trace-id" in response.headers`, not `"X-Trace-ID"`.

---

## Constraints

- **No new migrations.** Observability is entirely application-layer.
- **Middleware ordering:** TraceIdMiddleware must be outermost (added last via `add_middleware`) to ensure trace ID is set before any route handler or other middleware executes.
- **Pure ASGI middleware required:** `BaseHTTPMiddleware` buffers the full response body, which breaks the streaming SSE endpoint. Use the direct ASGI callable pattern instead.
- **Lazy Sentry import:** `import sentry_sdk` only inside the `if settings.sentry_dsn:` block. This keeps test startup fast and avoids a hard dependency on the package being configured.
- **Gateway protocol unchanged:** timing and logging go in `OpenRouterLlmGateway` only, not in the `LlmGateway` Protocol or `FakeLlmGateway` used in tests.
- **configure_logging() idempotency:** guard against double-adding handlers to avoid duplicate log output in tests that create multiple `TestClient` instances.

## Verification Checklist
- [ ] `210` existing tests pass.
- [ ] `5` new observability tests pass.
- [ ] Total: `215/215`.
- [ ] Ruff `E9,F63,F7,F82`: passing.
- [ ] Migration head unchanged: `20260223_0018`.
- [ ] `docs/sprint_week24_handoff.md` published.
