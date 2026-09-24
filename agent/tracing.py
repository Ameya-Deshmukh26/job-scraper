"""
Opik tracing.

One trace per agent run, with every node nested underneath it as a span.

`@traced` alone was not enough: LangGraph invokes each node as a separate
top-level call, so decorating nodes individually produced three disconnected
traces per run (load_corpus, tailor, validate_tailoring) rather than one
connected picture. `run_traced()` wraps the public entry points in graph.py so
the whole invocation happens inside one parent trace and the node spans nest
beneath it.

Everything here degrades to a no-op when Opik is unconfigured, so the graph
behaves identically with or without credentials and the test suite needs none.
"""
from __future__ import annotations

import functools
import logging
import os
import time

log = logging.getLogger(__name__)

OPIK_PROJECT = os.environ.get("OPIK_PROJECT_NAME", "job-scout-agent")
OPIK_WORKSPACE = os.environ.get("OPIK_WORKSPACE") or None
_ENABLED: bool | None = None


def opik_enabled() -> bool:
    """
    True if Opik has credentials (cloud or self-hosted) and imports cleanly.

    The credential check comes first on purpose: importing opik costs ~10s,
    which is far too slow to pay on a request just to learn it is unconfigured.
    That import once timed out /api/agent/status.
    """
    global _ENABLED
    if _ENABLED is not None:
        return _ENABLED

    # OPIK_API_KEY -> Comet cloud. OPIK_URL_OVERRIDE -> self-hosted instance.
    if not (os.environ.get("OPIK_API_KEY") or os.environ.get("OPIK_URL_OVERRIDE")):
        _ENABLED = False
        log.info("Opik not configured - tracing disabled. Set OPIK_API_KEY for "
                 "Comet cloud, or OPIK_URL_OVERRIDE=http://localhost:5173/api "
                 "for a self-hosted instance.")
        return _ENABLED

    try:
        import opik  # noqa: F401
        _ENABLED = True
        log.info(f"Opik tracing enabled - project {OPIK_PROJECT!r}"
                 + (f", workspace {OPIK_WORKSPACE!r}" if OPIK_WORKSPACE else ""))
    except ImportError:
        _ENABLED = False
        log.warning("OPIK credentials set but the opik package is not installed "
                    "(pip install opik); tracing disabled.")
    return _ENABLED


def reset_enabled_cache() -> None:
    """Re-read the environment. Used by tests and after configuring a key."""
    global _ENABLED, OPIK_WORKSPACE
    _ENABLED = None
    OPIK_WORKSPACE = os.environ.get("OPIK_WORKSPACE") or None


def run_traced(name: str, fn, **metadata):
    """
    Execute `fn()` inside one parent Opik trace and return its result.

    This takes a callable rather than being a context manager on purpose. An
    Opik trace is opened by *calling* a tracked function, so the work has to
    happen inside that call. A `with` block could only open and close the
    trace before the body ran, which is exactly the bug that produced three
    disconnected traces per run instead of one with nested spans.

    Node-level `@traced` spans invoked inside `fn` attach to this trace.
    Tracing problems never propagate: a broken exporter must not break a run.
    """
    t0 = time.perf_counter()
    try:
        if not opik_enabled():
            return fn()

        import opik

        @opik.track(name=name, project_name=OPIK_PROJECT)
        def _scope():
            try:
                opik.opik_context.update_current_trace(metadata=dict(metadata))
            except Exception:
                pass
            return fn()

        try:
            return _scope()
        except Exception as e:
            # Distinguish a tracing failure from a failure inside fn(): only
            # the former is safe to swallow.
            if e.__class__.__module__.startswith("opik"):
                log.debug(f"Opik run_traced({name}) failed, running untraced: {e}")
                return fn()
            raise
    finally:
        log.info(f"[trace] {name} {(time.perf_counter() - t0) * 1000:.0f}ms")


def update_trace(**metrics) -> None:
    """
    Attach run-level metrics to the parent trace.

    Node spans already carry their own metrics via log_metric; this puts the
    numbers that judge the whole run (accuracy, cost) where they are visible
    without expanding any spans.
    """
    if metrics:
        log.info("[trace-metrics] " + " ".join(f"{k}={v}" for k, v in metrics.items()))
    if not opik_enabled():
        return
    try:
        import opik
        opik.opik_context.update_current_trace(metadata=dict(metrics))
    except Exception as e:
        log.debug(f"Opik update_trace failed: {e}")


def traced(name: str | None = None, **span_kwargs):
    """
    Decorator: record the call as an Opik span when enabled, otherwise just
    time it and log. Safe to stack on every node.
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
    """Attach a metric to the current span (no-op when disabled)."""
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
