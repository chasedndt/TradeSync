"""Who may change state through this API, decided before any route runs.

Every change (POST, PUT, PATCH, DELETE) passes two checks, in order:

1. **Origin.** A browser names the page behind every change in the ``Origin``
   header, and a change from any page other than the Cockpit is refused.
   Binding the port to loopback does not prevent this one: any web page open on
   this machine can aim a request at 127.0.0.1, and FastAPI parses a body sent
   without a Content-Type as JSON, so a cross-site page could unpause paper
   entries or rewrite a Hermes job's schedule without ever reading a response
   (checked against FastAPI 0.115.2 on 2026-09-15). A request with no
   ``Origin`` did not come from a browser page (the host bridges, other
   containers, curl) and passes this check. ``STATE_API_ALLOWED_ORIGINS`` adds
   origins, comma-separated; ``*`` switches the check off, as a rollback lever.
2. **Operator token**, only when ``STATE_API_OPERATOR_TOKEN`` is set. Every
   change must then carry it in ``X-Operator-Token``. Unset keeps today's
   behaviour, with the loopback-bound ports as the control. Set but shorter
   than 32 characters refuses every change, rather than running unguarded
   while the operator believes otherwise.

Source addresses decide nothing. Docker NATs published ports, so a host bridge
on 127.0.0.1 and a stranger on the network would both arrive from the compose
gateway (172.18.0.1 in the 2026-09-15 access log).

``POST /webhook/tradingview`` is exempt from both checks. It is the one path the
Cloudflare tunnel publishes, TradingView can send neither header, and the route
authenticates each alert with the shared secret in its body.

``GET /state/access-policy`` reports what is enforced, never the token itself.
A refusal is logged with its method, path and status, never a header value.

The guard wraps the whole application (``app/asgi.py``), so it also covers
routes that other modules register later.
"""

from __future__ import annotations

import hmac
import logging
import os
from typing import Any, Iterable

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from tradesync_core.state_api_access import MIN_TOKEN_CHARS, TOKEN_ENV, TOKEN_HEADER, token_state

logger = logging.getLogger("state-api")

ORIGINS_ENV = "STATE_API_ALLOWED_ORIGINS"
GUARDED_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
EXEMPT_PATHS = frozenset({"/webhook/tradingview"})
POLICY_PATH = "/state/access-policy"
# The Cockpit as nginx serves it (or the Vite dev server on the same port), and
# state-api's own /docs page.
DEFAULT_ORIGINS = (
    "http://127.0.0.1:3000",
    "http://localhost:3000",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
)


def _origin(value: str) -> str:
    return value.strip().rstrip("/").lower()


class AccessGuard:
    """ASGI middleware: the origin check always, the operator token when one is configured."""

    def __init__(
        self, app: ASGIApp, *, token: str | None = None, allowed_origins: Iterable[str] | None = None
    ) -> None:
        self.app = app
        self._token = (os.getenv(TOKEN_ENV, "") if token is None else token).strip()
        self.token_state = token_state(self._token)
        extra = os.getenv(ORIGINS_ENV, "").split(",") if allowed_origins is None else list(allowed_origins)
        configured = {_origin(o) for o in (*DEFAULT_ORIGINS, *extra) if o.strip()}
        self.origin_check = "*" not in configured
        self.allowed_origins = frozenset(configured - {"*"})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        method, path = scope["method"].upper(), scope.get("path", "")
        if method == "GET" and path == POLICY_PATH:
            await JSONResponse(self.policy())(scope, receive, send)
            return
        if method in GUARDED_METHODS and path not in EXEMPT_PATHS:
            refusal = self.refusal(Headers(scope=scope))
            if refusal is not None:
                status, detail = refusal
                logger.warning("change refused: %s %r -> HTTP %s", method, path, status)
                await JSONResponse({"detail": detail, "authority": "none"}, status_code=status)(scope, receive, send)
                return
        await self.app(scope, receive, send)

    def refusal(self, headers: Headers) -> tuple[int, str] | None:
        """Why a change is refused, or None when it may reach its route."""
        origin = headers.get("origin")
        if self.origin_check and origin is not None and _origin(origin) not in self.allowed_origins:
            return 403, (
                "Change refused: it came from a web page that is not the TradeSync Cockpit. "
                f"GET {POLICY_PATH} lists the allowed origins; add one you trust to {ORIGINS_ENV}."
            )
        if self.token_state == "misconfigured":
            return 503, (
                f"Changes refused: {TOKEN_ENV} is set but shorter than {MIN_TOKEN_CHARS} characters. "
                "Correct it in runtime.env and recreate state-api."
            )
        if self.token_state == "required":
            # Starlette decodes header bytes as latin-1, so this recovers them exactly.
            supplied = headers.get(TOKEN_HEADER, "").encode("latin-1")
            if not hmac.compare_digest(supplied, self._token.encode("utf-8")):
                return 401, (
                    f"Operator token required for changes. Enter it in Cockpit Settings, or send it as {TOKEN_HEADER}."
                )
        return None

    def policy(self) -> dict[str, Any]:
        """What is enforced, for the Cockpit and for post-deploy checks."""
        return {
            "schema_version": "access_policy_v1",
            "operator_token": self.token_state,
            "token_header": TOKEN_HEADER,
            "guarded_methods": sorted(GUARDED_METHODS),
            "origin_check": "enforced" if self.origin_check else "disabled",
            "allowed_origins": sorted(self.allowed_origins),
            "exempt_paths": sorted(EXEMPT_PATHS),
            "note": (
                "A change sent from a browser page outside allowed_origins is refused. When operator_token is "
                "'required', every change must carry token_header. Source addresses are not used, because Docker "
                "NATs published ports. Reads are not guarded; the published ports are bound to 127.0.0.1."
            ),
        }
