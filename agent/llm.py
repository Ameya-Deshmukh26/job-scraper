"""
Pluggable LLM backend, resolved at runtime in priority order:

  1. sdk   claude-agent-sdk driving the Claude Code CLI - reuses the
           subscription/SSO login, no API key needed
  2. api   ANTHROPIC_API_KEY via langchain-anthropic
  3. none  no LLM available; callers fall back to deterministic behaviour

The graph runs end to end under all three. Only the quality of ranking
reasoning and bullet rewriting changes.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
from contextlib import aclosing

log = logging.getLogger(__name__)

MODEL = os.environ.get("JOB_AGENT_MODEL", "claude-sonnet-5")

# Usage from the most recent completion. The Claude Agent SDK reports real
# token counts and a billed cost on its ResultMessage, so cost tracing is
# measured rather than estimated.
LAST_USAGE: dict = {"input_tokens": 0, "output_tokens": 0,
                    "cache_read_tokens": 0, "cost_usd": 0.0}


def last_usage() -> dict:
    """Token counts and USD cost for the previous complete() call."""
    return dict(LAST_USAGE)


def _record_usage(usage: dict | None, cost) -> None:
    u = usage or {}
    LAST_USAGE.update(
        input_tokens=int(u.get("input_tokens") or 0),
        output_tokens=int(u.get("output_tokens") or 0),
        cache_read_tokens=int(u.get("cache_read_input_tokens") or 0),
        cost_usd=float(cost or 0.0),
    )


_BACKEND: str | None = None


def _cli_present() -> bool:
    if shutil.which("claude"):
        return True
    # Windows: npm global installs land here and may not be on this shell's PATH
    for p in (
        os.path.expandvars(r"%APPDATA%\npm\claude.cmd"),
        os.path.expandvars(r"%APPDATA%\npm\claude"),
    ):
        if os.path.exists(p):
            os.environ["PATH"] = os.path.dirname(p) + os.pathsep + os.environ.get("PATH", "")
            return True
    return False


def backend() -> str:
    """Which backend is live: 'sdk' | 'api' | 'none'."""
    global _BACKEND
    if _BACKEND is not None:
        return _BACKEND
    try:
        import claude_agent_sdk  # noqa: F401
        if _cli_present():
            _BACKEND = "sdk"
            log.info("LLM backend: claude-agent-sdk (subscription auth, no API key)")
            return _BACKEND
    except ImportError:
        pass
    if os.environ.get("ANTHROPIC_API_KEY"):
        _BACKEND = "api"
        log.info("LLM backend: anthropic API key")
        return _BACKEND
    _BACKEND = "none"
    log.warning("LLM backend: none - ranking uses heuristics, tailoring is corpus-verbatim")
    return _BACKEND


class AuthExpired(RuntimeError):
    """Claude Code OAuth session is expired; a one-time re-login is needed."""


def _complete_sdk(system: str, user: str) -> str:
    from claude_agent_sdk import ClaudeAgentOptions, query

    async def run() -> str:
        opts = ClaudeAgentOptions(
            system_prompt=system,
            max_turns=1,
            allowed_tools=[],           # pure text generation, no tool use
            permission_mode="bypassPermissions",
        )
        chunks: list[str] = []
        auth_failed = False
        # aclosing() finalizes the SDK's subprocess transport even when we
        # break out early, which otherwise floods stderr on teardown
        async with aclosing(query(prompt=user, options=opts)) as stream:
            async for msg in stream:
                if getattr(msg, "error", None) == "authentication_failed":
                    auth_failed = True
                    break
                # ResultMessage carries the run's real usage and billed cost
                if getattr(msg, "usage", None) is not None and not hasattr(msg, "content"):
                    _record_usage(msg.usage, getattr(msg, "total_cost_usd", 0.0))
                content = getattr(msg, "content", None)
                if isinstance(content, str):
                    chunks.append(content)
                elif isinstance(content, list):
                    for block in content:
                        text = getattr(block, "text", None)
                        if text:
                            chunks.append(text)
        if auth_failed:
            raise AuthExpired(
                "Claude Code OAuth session expired. Run `claude` once in a "
                "terminal and sign in, then this backend works with no API key."
            )
        return "".join(chunks).strip()

    try:
        return asyncio.run(run())
    except RuntimeError:                 # already inside a loop (Flask thread)
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(run())
        finally:
            loop.close()


def _complete_api(system: str, user: str) -> str:
    from langchain_anthropic import ChatAnthropic
    llm = ChatAnthropic(model=MODEL, max_tokens=2000, temperature=0)
    resp = llm.invoke([("system", system), ("human", user)])
    return (resp.content if isinstance(resp.content, str)
            else "".join(b.get("text", "") for b in resp.content)).strip()


def complete(system: str, user: str) -> str | None:
    """One-shot completion. Returns None when no backend is available."""
    global _BACKEND
    b = backend()
    try:
        if b == "sdk":
            return _complete_sdk(system, user)
        if b == "api":
            return _complete_api(system, user)
    except AuthExpired as e:
        # Don't retry on every node for the rest of the process
        log.error(str(e))
        _BACKEND = "none"
        return None
    except Exception as e:
        log.warning(f"LLM call failed ({b}): {e}")
        return None
    return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print("backend:", backend())
    out = complete("Reply with exactly one word.", "Say: working")
    print("response:", repr(out))
