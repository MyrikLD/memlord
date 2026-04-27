import logging
import secrets
import time
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import datetime, timezone
from urllib.parse import urlencode

import sqlalchemy as sa
from authlib.jose.errors import JoseError
from fastmcp.server.auth import OAuthProvider
from fastmcp.server.auth.auth import AccessToken
from fastmcp.server.auth.jwt_issuer import JWTIssuer, derive_jwt_key
from fastmcp.server.auth.redirect_validation import matches_allowed_pattern
from mcp.server.auth.provider import (
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    RefreshToken,
    TokenError,
    construct_redirect_uri,
)
from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyUrl, BaseModel
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.routing import Route

from memlord.auth import hash_password
from memlord.dao.user import UserDao
from memlord.models.oauth_client import OAuthClient
from memlord.models.revoked_token import RevokedToken
from memlord.utils.inject_client_id import InjectClientIdMiddleware

logger = logging.getLogger(__name__)


class _PatternMatchingClient(OAuthClientInformationFull):
    """OAuthClientInformationFull that matches redirect_uris by path, ignoring query string."""

    def validate_redirect_uri(self, redirect_uri: AnyUrl | None) -> AnyUrl:
        if redirect_uri is not None:
            uri_str = str(redirect_uri)
            for pattern in self.redirect_uris or []:
                if matches_allowed_pattern(uri_str, str(pattern)):
                    return redirect_uri
        return super().validate_redirect_uri(redirect_uri)


ACCESS_TOKEN_TTL = 3600  # 1 hour
REFRESH_TOKEN_TTL = 30 * 24 * 3600  # 30 days
AUTH_CODE_TTL = 300  # 5 minutes
PENDING_TTL = 600  # 10 minutes to complete login

_CARD_STYLE = """\
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: system-ui, sans-serif; background: #f5f5f5; color: #111;
       display: flex; align-items: center; justify-content: center; min-height: 100vh; }
.card { background: #fff; border: 1px solid #e5e7eb; border-radius: 12px;
        padding: 2rem; width: 100%; max-width: 380px;
        box-shadow: 0 2px 8px rgba(0,0,0,.08); }
h1 { font-size: 1.25rem; font-weight: 600; margin-bottom: 1.5rem; color: #111; }
label { display: block; font-size: 0.875rem; color: #555; margin-bottom: 0.375rem; }
input[type=email], input[type=password], input[type=text] {
    width: 100%; padding: 0.625rem 0.75rem;
    border: 1px solid #d1d5db; border-radius: 6px; color: #111;
    font-size: 0.875rem; outline: none; margin-bottom: 1rem; }
input:focus { border-color: #6366f1; }
button { width: 100%; margin-top: 0.25rem; padding: 0.625rem;
         background: #6366f1; border: none; border-radius: 6px;
         color: #fff; font-size: 0.875rem; font-weight: 500; cursor: pointer; }
button:hover { background: #4f46e5; }
.error { margin-top: 1rem; padding: 0.5rem 0.75rem; background: #fef2f2;
         border: 1px solid #f87171; border-radius: 6px;
         color: #dc2626; font-size: 0.8125rem; }
.meta { margin-top: 1rem; font-size: 0.75rem; color: #9ca3af; }
.hint { margin-bottom: 1rem; font-size: 0.8125rem; color: #6b7280; }
"""

_LOGIN_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Memlord — Sign in</title>
  <style>{style}</style>
</head>
<body>
  <div class="card">
    <h1>Memlord</h1>
    <form method="post">
      <input type="hidden" name="id" value="{pending_id}">
      <input type="hidden" name="action" value="login">
      <label for="email">Email</label>
      <input type="email" id="email" name="email" autofocus required
             autocomplete="email" value="{email}">
      <label for="pw">Password</label>
      <input type="password" id="pw" name="password" required
             autocomplete="current-password">
      <button type="submit">Sign in</button>
      {error_block}
    </form>
    <p class="meta">Client: {client_id}</p>
  </div>
</body>
</html>
"""

_REGISTER_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Memlord — Create account</title>
  <style>{style}</style>
</head>
<body>
  <div class="card">
    <h1>Create account</h1>
    <p class="hint">No account found for <strong>{email}</strong>. Create one to continue.</p>
    <form method="post">
      <input type="hidden" name="id" value="{pending_id}">
      <input type="hidden" name="action" value="register">
      <input type="hidden" name="email" value="{email}">
      <label for="display_name">Display name</label>
      <input type="text" id="display_name" name="display_name" autofocus required
             autocomplete="name">
      <label for="pw">Password</label>
      <input type="password" id="pw" name="password" required
             autocomplete="new-password">
      <label for="pw2">Confirm password</label>
      <input type="password" id="pw2" name="password2" required
             autocomplete="new-password">
      <button type="submit">Create account</button>
      {error_block}
    </form>
    <p class="meta">Client: {client_id}</p>
  </div>
</body>
</html>
"""


class _PendingAuth(BaseModel):
    client_id: str
    params: AuthorizationParams
    scopes: list[str]
    expires_at: float


class MemlordOAuthProvider(OAuthProvider):
    """Full in-process OAuth 2.1 authorization server with email+password login."""

    def __init__(
        self,
        base_url: str,
        jwt_secret: str,
        session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
    ) -> None:
        super().__init__(
            base_url=base_url,
            client_registration_options=ClientRegistrationOptions(
                enabled=True,
                valid_scopes=["mcp"],
                default_scopes=["mcp"],
            ),
            revocation_options=RevocationOptions(enabled=True),
            required_scopes=["mcp"],
        )
        self._base_url = base_url.rstrip("/")

        self._signing_key = derive_jwt_key(
            high_entropy_material=jwt_secret, salt="memlord-oauth-jwt"
        )
        self._jwt = JWTIssuer(
            issuer=self._base_url,
            audience=self._base_url,
            signing_key=self._signing_key,
        )

        self._auth_codes: dict[str, AuthorizationCode] = {}
        self._pending: dict[str, _PendingAuth] = {}

        self.session = session_factory

    # ------------------------------------------------------------------
    # Login page
    # ------------------------------------------------------------------

    def set_mcp_path(self, mcp_path: str | None) -> None:
        super().set_mcp_path(mcp_path)
        # Update JWT audience to the resource URL now that the MCP path is known.
        # Per RFC 8707, tokens must be bound to the resource they are issued for.
        audience = (
            str(self._resource_url).rstrip("/")
            if self._resource_url is not None
            else self._base_url
        )
        self._jwt = JWTIssuer(
            issuer=self._base_url,
            audience=audience,
            signing_key=self._signing_key,
        )
        logger.debug("set_mcp_path: JWT audience updated to %s", audience)

    def get_middleware(self) -> list:
        middlewares = super().get_middleware()
        middlewares.append(
            Middleware(InjectClientIdMiddleware, auth_codes=self._auth_codes)  # type: ignore[arg-type]
        )
        return middlewares

    def get_routes(self, mcp_path: str | None = None) -> list[Route]:
        routes = super().get_routes(mcp_path)
        routes += [Route("/login", endpoint=self._login, methods=["GET", "POST"])]

        # RFC 9728: alias path-specific well-known at root so both work.
        for route in list(routes):
            if isinstance(route, Route) and route.path.startswith(
                "/.well-known/oauth-protected-resource/"
            ):
                routes.append(
                    Route(
                        "/.well-known/oauth-protected-resource",
                        endpoint=route.endpoint,
                        methods=["GET", "OPTIONS"],
                    )
                )
                break

        return routes

    async def _login(self, request: Request) -> Response:
        if request.method == "GET":
            return self._login_get(request)
        return await self._login_post(request)

    def _login_get(self, request: Request) -> Response:
        pending_id = request.query_params.get("id", "")
        pending = self._pending.get(pending_id)
        if not pending or pending.expires_at < time.time():
            logger.warning("login GET: invalid/expired pending_id=%s...", pending_id[:8])
            return HTMLResponse(
                "<h3>Authorization request expired. Please try again.</h3>",
                status_code=400,
            )
        return HTMLResponse(
            _LOGIN_HTML.format(
                style=_CARD_STYLE,
                pending_id=pending_id,
                client_id=pending.client_id,
                email="",
                error_block="",
            )
        )

    async def _login_post(self, request: Request) -> Response:
        form = await request.form()
        pending_id = str(form.get("id", ""))
        action = str(form.get("action", "login"))

        pending = self._pending.get(pending_id)
        if not pending or pending.expires_at < time.time():
            self._pending.pop(pending_id, None)
            logger.warning("login POST: invalid/expired pending_id=%s...", pending_id[:8])
            return HTMLResponse(
                "<h3>Authorization request expired. Please try again.</h3>",
                status_code=400,
            )

        if action == "register":
            return await self._handle_register(form, pending_id, pending)
        return await self._handle_login(form, pending_id, pending)

    async def _handle_login(self, form, pending_id: str, pending: "_PendingAuth") -> Response:
        email = str(form.get("email", "")).strip().lower()
        password = str(form.get("password", ""))

        async with self.session() as s:
            exists = await UserDao(s).exists_by_email(email)
            if not exists:
                logger.info("login: email not found, showing register form email=%s", email)
                return HTMLResponse(
                    _REGISTER_HTML.format(
                        style=_CARD_STYLE,
                        pending_id=pending_id,
                        client_id=pending.client_id,
                        email=email,
                        error_block="",
                    )
                )
            user = await UserDao(s).authenticate(email, password)

        if user is None:
            logger.warning("login: wrong password email=%s client_id=%s", email, pending.client_id)
            return HTMLResponse(
                _LOGIN_HTML.format(
                    style=_CARD_STYLE,
                    pending_id=pending_id,
                    client_id=pending.client_id,
                    email=email,
                    error_block='<p class="error">Incorrect password.</p>',
                ),
                status_code=401,
            )

        return await self._issue_code(pending_id, pending, user.id)

    async def _handle_register(self, form, pending_id: str, pending: "_PendingAuth") -> Response:
        email = str(form.get("email", "")).strip().lower()
        display_name = str(form.get("display_name", "")).strip()
        password = str(form.get("password", ""))
        password2 = str(form.get("password2", ""))

        def _reg_error(msg: str) -> Response:
            return HTMLResponse(
                _REGISTER_HTML.format(
                    style=_CARD_STYLE,
                    pending_id=pending_id,
                    client_id=pending.client_id,
                    email=email,
                    error_block=f'<p class="error">{msg}</p>',
                ),
                status_code=400,
            )

        if not display_name:
            return _reg_error("Display name is required.")
        if not password:
            return _reg_error("Password is required.")
        if password != password2:
            return _reg_error("Passwords do not match.")

        async with self.session() as s:
            if await UserDao(s).exists_by_email(email):
                return _reg_error("An account with this email already exists.")
            user = await UserDao(s).create(
                email=email,
                display_name=display_name,
                hashed_password=hash_password(password),
            )

        logger.info("register: created user id=%d email=%s", user.id, email)
        return await self._issue_code(pending_id, pending, user.id)

    async def _issue_code(self, pending_id: str, pending: "_PendingAuth", user_id: int) -> Response:
        del self._pending[pending_id]

        # Link this OAuth client to the authenticated user
        async with self.session() as s:
            await s.execute(
                sa.update(OAuthClient)
                .where(OAuthClient.client_id == pending.client_id)
                .values(user_id=user_id)
            )

        code = secrets.token_urlsafe(32)
        self._auth_codes[code] = AuthorizationCode(
            code=code,
            client_id=pending.client_id,
            redirect_uri=pending.params.redirect_uri,
            redirect_uri_provided_explicitly=pending.params.redirect_uri_provided_explicitly,
            scopes=pending.scopes,
            expires_at=time.time() + AUTH_CODE_TTL,
            code_challenge=pending.params.code_challenge,
            resource=pending.params.resource,
        )
        redirect = construct_redirect_uri(
            str(pending.params.redirect_uri), code=code, state=pending.params.state
        )
        logger.info(
            "issue_code: success client_id=%s user_id=%d code=%s...",
            pending.client_id,
            user_id,
            code[:8],
        )
        return RedirectResponse(redirect, status_code=302)

    # ------------------------------------------------------------------
    # OAuthAuthorizationServerProvider
    # ------------------------------------------------------------------

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        async with self.session() as s:
            data = await s.scalar(
                sa.select(OAuthClient.data).where(OAuthClient.client_id == client_id)
            )

        if data is None:
            logger.warning("get_client: client_id=%s not found in DB", client_id)
            return None

        logger.info(
            "get_client: client_id=%s found auth_method=%s has_secret=%s",
            client_id,
            data.get("token_endpoint_auth_method"),
            bool(data.get("client_secret")),
        )
        return _PatternMatchingClient.model_validate(data)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if client_info.client_id is None:
            raise ValueError("client_id required")
        logger.info(
            "register_client client_id=%s redirect_uris=%s scope=%s",
            client_info.client_id,
            client_info.redirect_uris,
            client_info.scope,
        )
        data = client_info.model_dump(mode="json")
        if data.get("client_name") == "Glama":
            data["token_endpoint_auth_method"] = "client_secret_basic"
        async with self.session() as s:
            existing_data = await s.scalar(
                sa.select(OAuthClient.data).where(OAuthClient.client_id == client_info.client_id)
            )
            if existing_data:
                existing_uris: list[str] = existing_data.get("redirect_uris") or []
                new_uris: list[str] = data.get("redirect_uris") or []
                merged = list(dict.fromkeys(existing_uris + new_uris))
                data["redirect_uris"] = merged
                logger.info("register_client merged redirect_uris=%s", merged)
            await s.execute(
                pg_insert(OAuthClient)
                .values(client_id=client_info.client_id, data=data)
                .on_conflict_do_update(
                    index_elements=[OAuthClient.client_id],
                    set_={"data": data},
                )
            )

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        if client.client_id is None:
            raise AuthorizeError(
                error="unauthorized_client",
                error_description="Missing client_id",
            )

        scopes = list(params.scopes or [])
        if client.scope:
            allowed = set(client.scope.split())
            scopes = [s for s in scopes if s in allowed] or list(allowed)

        pending_id = secrets.token_urlsafe(32)
        self._pending[pending_id] = _PendingAuth(
            client_id=client.client_id,
            params=params,
            scopes=scopes,
            expires_at=time.time() + PENDING_TTL,
        )
        login_url = f"{self._base_url}/login?{urlencode({'id': pending_id})}"
        logger.info(
            "authorize → login client_id=%s pending=%s...",
            client.client_id,
            pending_id[:8],
        )
        return login_url

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        entry = self._auth_codes.get(authorization_code)
        if not entry or entry.client_id != client.client_id:
            return None
        if entry.expires_at < time.time():
            del self._auth_codes[authorization_code]
            return None
        return entry

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        if authorization_code.code not in self._auth_codes:
            raise TokenError("invalid_grant", "Code already used or expired")
        del self._auth_codes[authorization_code.code]
        if client.client_id is None:
            raise TokenError("invalid_client", "Missing client_id")
        token = self._issue_token_pair(client.client_id, authorization_code.scopes)
        logger.info(
            "exchange_authorization_code issued access=%s... scopes=%s",
            token.access_token[:16],
            token.scope,
        )
        return token

    async def load_access_token(self, token: str) -> AccessToken | None:  # type: ignore[override]
        try:
            claims = self._jwt.verify_token(token)
        except JoseError as exc:
            logger.debug("load_access_token JWT invalid: %s", exc)
            return None
        jti = claims.get("jti")
        if not jti:
            return None

        # Check revocation in DB (survives restarts, works cross-instance).
        async with self.session() as s:
            revoked = await s.scalar(sa.select(RevokedToken.jti).where(RevokedToken.jti == jti))
        if revoked is not None:
            logger.debug("load_access_token: jti revoked jti=%s...", jti[:8])
            return None

        client_id = claims.get("client_id", "")
        scopes = claims.get("scope", "").split() if claims.get("scope") else []
        exp = claims.get("exp")
        return AccessToken(
            token=token,
            client_id=client_id,
            scopes=scopes,
            expires_at=int(exp) if exp else None,
        )

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        try:
            claims = self._jwt.verify_token(refresh_token, expected_token_use="refresh")
        except JoseError as exc:
            logger.debug("load_refresh_token JWT invalid: %s", exc)
            return None
        token_client_id = claims.get("client_id", "")
        if token_client_id != client.client_id:
            return None
        scopes = claims.get("scope", "").split() if claims.get("scope") else []
        exp = claims.get("exp")
        logger.debug(
            "load_refresh_token: reconstructing from JWT claims (post-restart) client_id=%s",
            token_client_id,
        )
        return RefreshToken(
            token=refresh_token,
            client_id=token_client_id,
            scopes=scopes,
            expires_at=int(exp) if exp else None,
        )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        if scopes and not set(scopes).issubset(set(refresh_token.scopes)):
            raise TokenError("invalid_scope", "Requested scopes exceed original grant")
        effective_scopes = scopes or refresh_token.scopes
        await self._revoke_pair(refresh_token_str=refresh_token.token)
        if client.client_id is None:
            raise TokenError("invalid_client", "Missing client_id")
        token = self._issue_token_pair(client.client_id, effective_scopes)
        logger.info(
            "exchange_refresh_token issued access=%s... scopes=%s",
            token.access_token[:16],
            token.scope,
        )
        return token

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:  # type: ignore[override]
        logger.info("revoke_token type=%s", type(token).__name__)
        if isinstance(token, AccessToken):
            await self._revoke_pair(access_token_str=token.token)
        else:
            await self._revoke_pair(refresh_token_str=token.token)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _issue_token_pair(self, client_id: str, scopes: list[str]) -> OAuthToken:
        jti = secrets.token_urlsafe(32)
        access_str = self._jwt.issue_access_token(
            client_id=client_id, scopes=scopes, jti=jti, expires_in=ACCESS_TOKEN_TTL
        )

        refresh_jti = secrets.token_urlsafe(32)
        refresh_str = self._jwt.issue_refresh_token(
            client_id=client_id,
            scopes=scopes,
            jti=refresh_jti,
            expires_in=REFRESH_TOKEN_TTL,
        )

        return OAuthToken(
            access_token=access_str,
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_TTL,
            refresh_token=refresh_str,
            scope=" ".join(scopes),
        )

    async def _revoke_pair(
        self,
        access_token_str: str | None = None,
        refresh_token_str: str | None = None,
    ) -> None:
        to_revoke: list[tuple[str, datetime]] = []
        for token_str, token_use in [
            (access_token_str, "access"),
            (refresh_token_str, "refresh"),
        ]:
            if token_str is None:
                continue
            try:
                claims = self._jwt.verify_token(token_str, expected_token_use=token_use)
                jti = claims.get("jti")
                exp = claims.get("exp")
                if jti:
                    expires_at = datetime.fromtimestamp(
                        exp if exp else time.time() + REFRESH_TOKEN_TTL,
                        tz=timezone.utc,
                    ).replace(tzinfo=None)
                    to_revoke.append((jti, expires_at))
            except JoseError:
                pass

        if to_revoke:
            async with self.session() as s:
                for jti, expires_at in to_revoke:
                    await s.execute(
                        pg_insert(RevokedToken)
                        .values(jti=jti, expires_at=expires_at)
                        .on_conflict_do_nothing()
                    )
