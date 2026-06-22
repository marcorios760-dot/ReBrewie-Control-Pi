"""
Lightweight app login for remote Cloudflare Tunnel access.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .config import settings
from .registration import load_owner_registration

SESSION_COOKIE = "rebrewie_session"
PUBLIC_PATHS = ("/login", "/register", "/static/")
PBKDF2_ITERATIONS = 260_000


@dataclass(frozen=True)
class LoginResult:
    ok: bool
    reason: str = ""


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return (
        f"pbkdf2_sha256${PBKDF2_ITERATIONS}$"
        f"{base64.urlsafe_b64encode(salt).decode()}$"
        f"{base64.urlsafe_b64encode(digest).decode()}"
    )


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        scheme, iterations_s, salt_s, digest_s = stored_hash.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_s.encode())
        expected = base64.urlsafe_b64decode(digest_s.encode())
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            int(iterations_s),
        )
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def _session_secret() -> bytes:
    owner = load_owner_registration()
    secret = owner.get("session_secret") if owner else settings.auth_session_secret
    if not secret:
        secret = (owner or {}).get("password_hash") or settings.auth_password_hash or "rebrewie-local-dev-session"
    return secret.encode("utf-8")


def auth_required() -> bool:
    return settings.auth_enabled or load_owner_registration() is not None


def is_remote_request(request: Request) -> bool:
    host = (request.headers.get("x-forwarded-host") or request.url.hostname or "").split(":")[0]
    public_host = settings.remote_public_hostname.strip().lower()
    if public_host and host.lower() == public_host:
        return True
    return bool(public_host and host.lower().endswith("." + public_host))


def request_requires_auth(request: Request) -> bool:
    if not auth_required():
        return False
    if is_remote_request(request):
        return settings.auth_require_for_remote
    return settings.auth_require_for_local


def registration_required() -> bool:
    if not settings.auth_allow_initial_registration:
        return False
    if load_owner_registration() is not None:
        return False
    return settings.auth_enabled and not settings.auth_password_hash


def active_credentials() -> tuple[str, str]:
    owner = load_owner_registration()
    if owner:
        return owner["username"], owner["password_hash"]
    return settings.auth_username, settings.auth_password_hash


def create_session_token(username: str) -> str:
    expires = int(time.time() + max(1, settings.auth_session_hours) * 3600)
    payload = f"{username}|{expires}"
    sig = hmac.new(_session_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}|{sig}".encode("utf-8")).decode("ascii")


def read_session_token(token: str | None) -> str | None:
    if not token:
        return None
    try:
        decoded = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        username, expires_s, sig = decoded.rsplit("|", 2)
        payload = f"{username}|{expires_s}"
        expected = hmac.new(_session_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        if int(expires_s) < int(time.time()):
            return None
        return username
    except Exception:
        return None


def check_login(username: str, password: str) -> LoginResult:
    if not auth_required():
        return LoginResult(False, "Login is not enabled.")
    active_username, password_hash = active_credentials()
    if not password_hash:
        return LoginResult(False, "Register the owner account before logging in.")
    if not hmac.compare_digest(username, active_username):
        return LoginResult(False, "Invalid username or password.")
    if not verify_password(password, password_hash):
        return LoginResult(False, "Invalid username or password.")
    return LoginResult(True)


def set_session_cookie(response, username: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        create_session_token(username),
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        max_age=max(1, settings.auth_session_hours) * 3600,
        path="/",
    )


def clear_session_cookie(response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


def current_user(request: Request) -> str | None:
    if not auth_required():
        return active_credentials()[0]
    return read_session_token(request.cookies.get(SESSION_COOKIE))


def _wants_html(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return "text/html" in accept or request.url.path == "/"


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith(PUBLIC_PATHS) or not request_requires_auth(request):
            return await call_next(request)

        if registration_required():
            if _wants_html(request):
                return RedirectResponse("/register", status_code=303)
            return JSONResponse({"detail": "Owner registration required"}, status_code=403)

        user = current_user(request)
        if user:
            request.state.current_user = user
            return await call_next(request)

        if _wants_html(request):
            return RedirectResponse(f"/login?next={path}", status_code=303)
        return JSONResponse({"detail": "Authentication required"}, status_code=401)
