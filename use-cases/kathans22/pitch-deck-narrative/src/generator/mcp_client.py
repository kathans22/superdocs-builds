"""Thin wrapper over the SuperDocs MCP client — ported from Build 1.

Connects over streamable HTTP with bearer auth. Named errors name the cause and the fix.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from contextlib import AsyncExitStack

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

logger = logging.getLogger(__name__)

MCP_URL = os.environ.get("SUPERDOCS_MCP_URL", "https://api.superdocs.app/mcp/")

# httpx2.AsyncClient defaults to a 5-second timeout, which would silently cancel
# a legitimate multi-minute SuperDocs call before our own generous ceiling ever
# applies. Override it here so the transport layer imposes no timeout of its own;
# _call_tool's own ceiling is the single place a timeout is enforced.
_TRANSPORT_TIMEOUT = httpx2.Timeout(None)

# SuperDocs calls legitimately run 30 seconds to several minutes with no visible
# progress; this is a safety net against a genuinely hung call, not a normal
# operating limit. It must never be tight enough to cancel a working call.
DEFAULT_CALL_TIMEOUT_SECONDS = 900.0

# Transport-layer failures only — a connection that was never established or
# broke mid-flight. A slow-but-live response is never one of these, so it is
# never retried; only a demonstrable transport failure is.
_TRANSPORT_ERRORS = (
    httpx2.TransportError,
    httpx2.ConnectError,
    httpx2.ReadError,
    httpx2.WriteError,
    httpx2.RemoteProtocolError,
    ConnectionError,
)
_TRANSPORT_RETRY_ATTEMPTS = 3
_TRANSPORT_RETRY_BACKOFF_SECONDS = 2.0


class SuperDocsClientError(RuntimeError):
    """Raised with the cause and the fix, never just a status code."""


def _api_key() -> str:
    key = os.environ.get("SUPERDOCS_API_KEY")
    if not key:
        raise SuperDocsClientError(
            "SUPERDOCS_API_KEY is not set. Fix: copy .env.example to .env and set "
            "SUPERDOCS_API_KEY to your SuperDocs key (starts with 'sk_'), or export it "
            "in your shell before running."
        )
    if key.strip() in {"", "your-key-here"}:
        raise SuperDocsClientError(
            "SUPERDOCS_API_KEY is still the placeholder. Fix: replace your-key-here "
            "with a real sk_ key from use.superdocs.app → Settings → API Keys."
        )
    return key


class SuperDocsClient:
    """Connects to the SuperDocs MCP server over streamable HTTP with bearer auth."""

    def __init__(
        self,
        url: str | None = None,
        call_timeout: float = DEFAULT_CALL_TIMEOUT_SECONDS,
    ):
        self._url = url or MCP_URL
        self._call_timeout = call_timeout
        self._exit_stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

    async def __aenter__(self) -> SuperDocsClient:
        await self.connect()
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.close()

    async def connect(self) -> None:
        api_key = _api_key()
        headers = {"Authorization": f"Bearer {api_key}"}
        self._exit_stack = AsyncExitStack()
        http_client = httpx2.AsyncClient(headers=headers, timeout=_TRANSPORT_TIMEOUT)
        await self._exit_stack.enter_async_context(http_client)
        read, write = await self._exit_stack.enter_async_context(
            streamable_http_client(self._url, http_client=http_client)
        )
        # read_timeout_seconds=None: the session layer imposes no timeout of its
        # own either — _call_tool's ceiling is the single enforced timeout.
        session = await self._exit_stack.enter_async_context(
            ClientSession(read, write, read_timeout_seconds=None)
        )
        await session.initialize()
        self._session = session

    async def close(self) -> None:
        if self._exit_stack is not None:
            await self._exit_stack.aclose()
        self._exit_stack = None
        self._session = None

    async def _call_tool(self, name: str, arguments: dict) -> dict:
        if self._session is None:
            raise SuperDocsClientError(
                f"Cannot call '{name}': not connected. Fix: use "
                "'async with SuperDocsClient() as client:' or call connect() first."
            )

        attempt = 0
        while True:
            attempt += 1
            started = time.monotonic()
            try:
                result = await asyncio.wait_for(
                    self._session.call_tool(name, arguments), timeout=self._call_timeout
                )
            except asyncio.TimeoutError as exc:
                elapsed = time.monotonic() - started
                raise SuperDocsClientError(
                    f"SuperDocs tool '{name}' exceeded the {self._call_timeout:.0f}s ceiling "
                    f"after {elapsed:.0f}s. This is a safety net against a hung call, not a "
                    "normal failure — SuperDocs calls legitimately run for minutes. Fix: check "
                    "the session/job state on SuperDocs before retrying; the original call may "
                    "still be running server-side, so do not blindly re-call."
                ) from exc
            except _TRANSPORT_ERRORS as exc:
                elapsed = time.monotonic() - started
                logger.warning(
                    "SuperDocs tool '%s' transport failure after %.1fs (attempt %d/%d): %s",
                    name,
                    elapsed,
                    attempt,
                    _TRANSPORT_RETRY_ATTEMPTS,
                    exc,
                )
                if attempt >= _TRANSPORT_RETRY_ATTEMPTS:
                    raise SuperDocsClientError(
                        f"SuperDocs tool '{name}' failed after {attempt} transport-level "
                        f"attempts: {exc}. Fix: check network connectivity to {self._url} and "
                        "that the SuperDocs MCP server is reachable, then retry."
                    ) from exc
                await asyncio.sleep(_TRANSPORT_RETRY_BACKOFF_SECONDS * attempt)
                continue
            else:
                elapsed = time.monotonic() - started
                logger.info("SuperDocs tool '%s' completed in %.1fs", name, elapsed)
                break

        is_error = getattr(result, "is_error", getattr(result, "isError", False))
        if is_error:
            detail = _first_text(result.content) or "no error detail returned"
            raise SuperDocsClientError(
                f"SuperDocs tool '{name}' returned an error: {detail}"
            )
        structured_content = getattr(
            result, "structured_content", getattr(result, "structuredContent", None)
        )
        if structured_content is not None:
            return structured_content
        text = _first_text(result.content)
        if text is None:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"text": text}


def _first_text(content) -> str | None:
    for block in content or []:
        text = getattr(block, "text", None)
        if text is not None:
            return text
    return None
