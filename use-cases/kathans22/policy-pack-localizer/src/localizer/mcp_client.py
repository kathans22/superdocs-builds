"""Thin wrapper over the SuperDocs MCP client used by every other module."""

from __future__ import annotations

import os
from contextlib import AsyncExitStack

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

MCP_URL = "https://api.superdocs.app/mcp/"

# httpx2.AsyncClient defaults to a 5-second timeout, which would silently cancel
# a legitimate multi-minute SuperDocs call before our own generous ceiling ever
# applies. Override it here so the transport layer imposes no timeout of its own;
# _call_tool's own ceiling is the single place a timeout is enforced.
_TRANSPORT_TIMEOUT = httpx2.Timeout(None)


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
    return key


class SuperDocsClient:
    """Connects to the SuperDocs MCP server over streamable HTTP with bearer auth.

    Exposes exactly four operations as thin methods: upload, chat, approve, export.
    Everything else on the SuperDocs MCP surface is optional depth not built here.
    """

    def __init__(self, url: str = MCP_URL):
        self._url = url
        self._exit_stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

    async def __aenter__(self) -> "SuperDocsClient":
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
