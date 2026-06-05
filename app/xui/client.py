"""Async HTTP client for the 3x-ui panel REST API.

The 3x-ui panel authenticates with a session cookie returned from ``POST /login``.
This module wraps :class:`httpx.AsyncClient` with:

- Automatic login on first call.
- **CSRF bootstrap**: newer 3x-ui (the React-rewrite major version) embeds a
  per-session CSRF token in a ``<meta name="csrf-token">`` tag on the panel
  root page and rejects ``POST /login`` (and every mutating API call) with
  HTTP ``403`` unless the token is echoed in the ``X-CSRF-Token`` header.
  :meth:`XuiClient.login` first GETs the root to grab the token + session
  cookie, then sends it on login and on every subsequent request. Older
  panels have no such tag — a missing token is tolerated (cookie-only flow).
- Transparent re-login on ``401`` / ``403`` or on JSON envelopes whose ``msg``
  field hints at an expired session (e.g. ``"login"``).
- Uniform response parsing: 3x-ui returns ``{success, msg, obj}`` envelopes;
  :meth:`XuiClient.request_json` unwraps ``obj`` or raises :class:`XuiError`.

Usage::

    from app.xui import get_xui_client

    client = await get_xui_client()
    inbounds = await client.request_json("GET", "/panel/api/inbounds/list")

The module also exposes a process-wide singleton via
:func:`get_xui_client` / :func:`close_xui_client`.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import httpx
from loguru import logger

from app.config import settings

# Matches the per-session CSRF token the panel embeds in the root HTML:
#   <meta name="csrf-token" content="...">
# Tolerant of attribute order / whitespace; searches raw bytes so we never
# force a full-body decode of the (potentially large) HTML page.
_CSRF_META_RE = re.compile(
    rb"""<meta[^>]*name=["']csrf-token["'][^>]*content=["']([^"']+)["']""",
    re.IGNORECASE,
)

# Reasonable defaults for the panel — it lives in the same VPC most of the time
# but we still want a hard ceiling so a hung backend cannot stall the bot.
_DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=10.0)


class XuiError(RuntimeError):
    """Raised when the panel returns ``success=false`` or an invalid envelope.

    The string form contains the panel-provided ``msg`` (or an HTTP/status hint)
    so the message is safe to surface to operators in logs.
    """


class XuiClient:
    """Async client for the 3x-ui panel REST API.

    Holds a single :class:`httpx.AsyncClient` and an authenticated session
    cookie. The class is safe to share across coroutines; concurrent calls
    that race into ``login()`` are serialised through an internal lock so
    only one re-login happens per cookie expiry.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        verify_ssl: bool | None = None,
        timeout: httpx.Timeout | float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._base_url = (base_url or settings.XUI_BASE_URL).rstrip("/")
        self._username = username or settings.XUI_USERNAME
        self._password = password or settings.XUI_PASSWORD
        verify = settings.XUI_VERIFY_SSL if verify_ssl is None else verify_ssl

        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout,
            verify=verify,
            follow_redirects=True,
        )
        self._login_lock = asyncio.Lock()
        self._logged_in = False
        self._csrf_token: str | None = None

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    async def close(self) -> None:
        """Close the underlying HTTP client and release the connection pool."""
        await self._http.aclose()

    async def __aenter__(self) -> "XuiClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: D401 (context-mgr)
        await self.close()

    # ------------------------------------------------------------------ #
    # Auth
    # ------------------------------------------------------------------ #
    async def _bootstrap_session(self) -> None:
        """GET the panel root to capture the session cookie + CSRF token.

        Stores the ``<meta name="csrf-token">`` value (if present) on
        ``self._csrf_token`` so :meth:`login` and :meth:`request` can echo
        it in the ``X-CSRF-Token`` header. Older panels without the tag
        leave the token ``None`` and the cookie-only flow still works.

        A bootstrap transport failure is fatal (we cannot reach the panel
        at all); a missing token is not (older panels).
        """
        try:
            resp = await self._http.get("/")
        except httpx.HTTPError as exc:  # network / TLS failure
            raise XuiError(f"csrf bootstrap transport error: {exc!s}") from exc

        token: str | None = None
        match = _CSRF_META_RE.search(resp.content)
        if match:
            token = match.group(1).decode("ascii", "ignore") or None
        self._csrf_token = token
        logger.debug(
            "xui: csrf bootstrap — {}", "token captured" if token else "no token (legacy panel)"
        )

    def _csrf_headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        """Merge the CSRF header (when known) into ``extra`` headers."""
        headers = dict(extra or {})
        if self._csrf_token:
            headers.setdefault("X-CSRF-Token", self._csrf_token)
        return headers

    async def login(self) -> None:
        """Perform ``POST /login`` and store the session cookie on the client.

        Serialised through ``_login_lock`` so concurrent callers wait for a
        single round-trip. Bootstraps the CSRF token first (see
        :meth:`_bootstrap_session`) and echoes it in the ``X-CSRF-Token``
        header. Raises :class:`XuiError` if the panel rejects the
        credentials or returns an unexpected payload.
        """
        async with self._login_lock:
            logger.debug("xui: logging in as {}", self._username)
            await self._bootstrap_session()
            try:
                resp = await self._http.post(
                    "/login",
                    data={"username": self._username, "password": self._password},
                    headers=self._csrf_headers(),
                )
            except httpx.HTTPError as exc:  # network / TLS failure
                raise XuiError(f"login transport error: {exc!s}") from exc

            if resp.status_code != 200:
                raise XuiError(
                    f"login HTTP {resp.status_code}: {resp.text.strip()[:200]}"
                )

            try:
                payload: dict[str, Any] = resp.json()
            except ValueError as exc:
                raise XuiError(f"login: non-JSON response: {resp.text[:200]!r}") from exc

            if not payload.get("success"):
                raise XuiError(
                    f"login rejected by panel: {payload.get('msg') or payload!r}"
                )

            # httpx stores Set-Cookie automatically on the client's cookie jar.
            # We just record that we're authenticated.
            self._logged_in = True
            logger.info("xui: login OK ({} cookies stored)", len(self._http.cookies.jar))

    # ------------------------------------------------------------------ #
    # Request helpers
    # ------------------------------------------------------------------ #
    async def request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Send an HTTP request with auto-login + single retry on 401.

        ``path`` must be an API path starting with ``/`` — it is joined with
        the configured ``base_url``. The method will:

        1. Ensure we're logged in (perform initial login if not).
        2. Issue the request.
        3. If the response is ``401`` OR the JSON envelope hints at a lost
           session, re-login and retry **once**.

        Returns the raw :class:`httpx.Response` for callers that need
        binary/non-JSON payloads. Most code should prefer
        :meth:`request_json`.
        """
        if not self._logged_in:
            await self.login()

        caller_headers = kwargs.pop("headers", None)
        resp = await self._http.request(
            method, path, headers=self._csrf_headers(caller_headers), **kwargs
        )

        if self._needs_relogin(resp):
            logger.info("xui: session expired on {} {} — re-logging in", method, path)
            self._logged_in = False
            await self.login()
            # Rebuild from the caller's headers so the freshly-bootstrapped
            # CSRF token replaces the stale one rather than being skipped.
            resp = await self._http.request(
                method, path, headers=self._csrf_headers(caller_headers), **kwargs
            )

        return resp

    async def request_json(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> Any:
        """Send a request and return the unwrapped ``obj`` field of the envelope.

        Raises :class:`XuiError` if:
        - HTTP status is non-2xx (after the auto re-login retry).
        - Response is not valid JSON.
        - JSON envelope has ``success=false``.
        """
        resp = await self.request(method, path, **kwargs)
        return self._parse(resp)

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    @staticmethod
    def _needs_relogin(resp: httpx.Response) -> bool:
        """Detect whether a response indicates a lost / invalid session.

        ``401`` is the classic expired-cookie signal. ``403`` is added for
        the new panel: a stale / missing CSRF token (e.g. after the session
        rotated) is rejected with ``403`` — re-login re-bootstraps a fresh
        token, so a single retry recovers transparently.
        """
        if resp.status_code in (401, 403):
            return True
        # 3x-ui sometimes returns 200 with success=false and a "please login"
        # style message when the cookie is missing or invalid. Detect that
        # cheaply without forcing JSON parsing on every call site.
        if resp.status_code == 200 and resp.headers.get("content-type", "").startswith(
            "application/json"
        ):
            try:
                payload = resp.json()
            except ValueError:
                return False
            if isinstance(payload, dict) and payload.get("success") is False:
                msg = str(payload.get("msg") or "").lower()
                if "login" in msg or "session" in msg or "unauthor" in msg:
                    return True
        return False

    @staticmethod
    def _parse(resp: httpx.Response) -> Any:
        """Validate and unwrap a 3x-ui JSON envelope.

        Returns the value of the ``obj`` field on success. Raises
        :class:`XuiError` with a useful message on any failure mode.
        """
        if resp.status_code // 100 != 2:
            raise XuiError(
                f"HTTP {resp.status_code} on {resp.request.method} "
                f"{resp.request.url}: {resp.text.strip()[:200]}"
            )

        try:
            payload: Any = resp.json()
        except ValueError as exc:
            raise XuiError(
                f"non-JSON response on {resp.request.method} {resp.request.url}: "
                f"{resp.text[:200]!r}"
            ) from exc

        if not isinstance(payload, dict):
            raise XuiError(f"unexpected envelope shape (not an object): {payload!r}")

        if not payload.get("success"):
            raise XuiError(
                f"panel error on {resp.request.method} {resp.request.url}: "
                f"{payload.get('msg') or payload!r}"
            )

        return payload.get("obj")


# ---------------------------------------------------------------------- #
# Singleton factory
# ---------------------------------------------------------------------- #

_singleton: XuiClient | None = None
_singleton_lock = asyncio.Lock()


async def get_xui_client() -> XuiClient:
    """Return the process-wide :class:`XuiClient`, creating it lazily.

    Safe to call concurrently — initialisation is serialised through an
    asyncio lock. The instance is closed via :func:`close_xui_client` on
    application shutdown.
    """
    global _singleton
    if _singleton is not None:
        return _singleton
    async with _singleton_lock:
        if _singleton is None:
            _singleton = XuiClient()
    return _singleton


async def close_xui_client() -> None:
    """Close the process-wide client (no-op if not initialised)."""
    global _singleton
    if _singleton is not None:
        await _singleton.close()
        _singleton = None
