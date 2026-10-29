"""Default-deny authentication for every HTTP request.

A route used to be protected only if it remembered to ask for the caller
(Depends(get_principal)); a new route that forgot was open to anyone. This middleware
turns that around: every request must carry a valid Bearer access token unless its
path is on the public allowlist (settings.auth_public_paths, plus the API docs when
DOCS_ENABLED=true). CORS preflights (OPTIONS) always pass.

It only AUTHENTICATES: the verified Principal is put on request.state.principal, and
role checks stay in the routes (Depends(require_roles(...))).

Pure ASGI on purpose: Starlette's BaseHTTPMiddleware buffers request bodies and breaks
streaming uploads and background tasks."""

from collections.abc import Callable, Iterable
from typing import Any

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from src.core.rbac.tokens import InvalidTokenError

DOCS_PATHS = ("/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json")
UNAUTHORIZED_DETAIL = "Not signed in or session expired."


def bearer_token(scope: Scope) -> str | None:
    value = Headers(scope=scope).get("authorization", "")
    scheme, _, token = value.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def normalise(path: str) -> str:
    return path.rstrip("/") or "/"


class AuthMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        verify: Callable[[str], Any],
        public_paths: Iterable[str],
        docs_enabled: bool = False,
    ) -> None:
        self.app = app
        self.verify = verify  # token -> principal; raises InvalidTokenError
        public = {normalise(p) for p in public_paths}
        if docs_enabled:
            public.update(DOCS_PATHS)
        self.public = frozenset(public)

    def is_public(self, method: str, path: str) -> bool:
        return method == "OPTIONS" or normalise(path) in self.public

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self.is_public(scope["method"], scope["path"]):
            await self.app(scope, receive, send)
            return
        token = bearer_token(scope)
        if token is None:
            await self.reject(scope, receive, send)
            return
        try:
            principal = self.verify(token)
        except InvalidTokenError:
            await self.reject(scope, receive, send)
            return
        scope.setdefault("state", {})["principal"] = (
            principal  # -> request.state.principal
        )
        await self.app(scope, receive, send)

    @staticmethod
    async def reject(scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            status_code=401,
            content={"detail": UNAUTHORIZED_DETAIL, "code": "unauthorized"},
            headers={"WWW-Authenticate": "Bearer"},
        )
        await response(scope, receive, send)
