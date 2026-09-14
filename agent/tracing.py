"""
Opik tracing — every LLM call and node execution gets a span.

Degrades to a no-op if Opik is not configured, so the graph runs the same
with or without observability wired up.
"""
from __future__ import annotations

import functools
import logging
import os
import time

log = logging.getLogger(__name__)

OPIK_PROJECT = os.environ.get("OPIK_PROJECT_NAME", "job-scout-agent")
_ENABLED: bool | None = None


def opik_enabled() -> bool:
    """
    True if Opik has credentials (cloud or self-hosted) and imports.

    The credential check comes first on purpose: importing opik costs ~10s,
    which is far too slow to pay on a request just to learn it is unconfigured.
    """
    global _ENABLED
    if _ENABLED is not None:
        return _ENABLED

    if not (os.environ.get("OPIK_API_KEY")
            or os.environ.get("OPIK_URL_OVERRIDE")
            or os.environ.get("OPIK_LOCAL")):
        _ENABLED = False
        log.info("Opik not configured - tracing disabled. Set OPIK_API_KEY, "
                 "or OPIK_URL_OVERRIDE=http://localhost:5173/api for self-hosted.")
        return _ENABLED

    try:
        import opik  # noqa: F401
        _ENABLED = True
    except ImportError:
        _ENABLED = False
    return _ENABLED


def traced(name: str | None = None, **span_kwargs):
    """
    Decorator: record the call as an Opik span when enabled, otherwise
    just time it and log. Safe to stack on every node.
    """
    def decorator(fn):
        span_name = name or fn.__name__

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            t0 = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            finally:
                ms = (time.perf_counter() - t0) * 1000
                log.info(f"[span] {span_name} {ms:.0f}ms")

        if not opik_enabled():
            return wrapper
        try:
            import opik
            return opik.track(name=span_name, project_name=OPIK_PROJECT,
                              **span_kwargs)(wrapper)
        except Exception as e:      # never let tracing break the graph
            log.debug(f"Opik track failed for {span_name}: {e}")
            return wrapper

    return decorator


def log_metric(name: str, value, **meta):
    """Attach a metric to the current trace (no-op when disabled)."""
    log.info(f"[metric] {name}={value}" + (f" {meta}" if meta else ""))
    if not opik_enabled():
        return
    try:
        import opik
        span = opik.opik_context.get_current_span_data()
        if span:
            opik.opik_context.update_current_span(
                metadata={**(span.metadata or {}), name: value, **meta}
            )
    except Exception:
        pass
