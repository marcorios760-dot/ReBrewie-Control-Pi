"""Optional Blink camera snapshot support.

Blink does not provide a LAN RTSP-style live stream through blinkpy. This
module exposes a cached JPEG snapshot and refreshes it no faster than once per
minute so the Progress page can show a live-ish view without hammering Blink's
cloud API.
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path

from .config import settings

MIN_REFRESH_SECONDS = 60


class BlinkCameraError(RuntimeError):
    """Raised when the optional Blink integration cannot return an image."""


@dataclass
class BlinkSnapshot:
    image: bytes
    camera_name: str
    refreshed_at: float


class BlinkCameraService:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._blink = None
        self._snapshot: BlinkSnapshot | None = None
        self._last_error: str | None = None

    @property
    def refresh_seconds(self) -> int:
        return max(MIN_REFRESH_SECONDS, int(settings.blink_refresh_seconds or MIN_REFRESH_SECONDS))

    def status(self) -> dict:
        return {
            "enabled": settings.blink_enabled,
            "configured": bool(settings.blink_username and settings.blink_password),
            "camera_name": settings.blink_camera_name or None,
            "auth_file": settings.blink_auth_file,
            "auth_file_exists": Path(settings.blink_auth_file).exists(),
            "refresh_seconds": self.refresh_seconds,
            "has_snapshot": self._snapshot is not None,
            "refreshed_at": self._snapshot.refreshed_at if self._snapshot else None,
            "last_error": self._last_error,
        }

    async def get_snapshot(self) -> BlinkSnapshot:
        if not settings.blink_enabled:
            raise BlinkCameraError("Blink camera feed is disabled")
        if not settings.blink_username or not settings.blink_password:
            raise BlinkCameraError("Blink username/password are not configured")

        async with self._lock:
            now = time.time()
            if self._snapshot and now - self._snapshot.refreshed_at < self.refresh_seconds:
                return self._snapshot

            try:
                snapshot = await self._refresh_snapshot()
            except Exception as exc:  # Keep the Progress page usable on camera errors.
                self._last_error = self._format_error(exc)
                if self._snapshot:
                    return self._snapshot
                raise BlinkCameraError(self._last_error) from exc

            self._snapshot = snapshot
            self._last_error = None
            return snapshot

    async def _refresh_snapshot(self) -> BlinkSnapshot:
        blink = await self._get_blink()
        camera = self._select_camera(blink.cameras)

        snap_picture = getattr(camera, "snap_picture", None)
        if callable(snap_picture):
            await snap_picture()

        await blink.refresh()
        image = getattr(camera, "image_from_cache", None)
        if not image:
            await blink.refresh(force=True)
            image = getattr(camera, "image_from_cache", None)

        if not image:
            raise BlinkCameraError("No Blink camera snapshot is available yet")

        return BlinkSnapshot(bytes(image), getattr(camera, "name", settings.blink_camera_name), time.time())

    async def _get_blink(self):
        if self._blink is not None:
            return self._blink

        try:
            from aiohttp import ClientSession
            from blinkpy.auth import Auth
            from blinkpy.blinkpy import Blink
            from blinkpy.auth import BlinkTwoFARequiredError
            import blinkpy.api as blink_api
        except ImportError as exc:
            raise BlinkCameraError("blinkpy is not installed; run pip install -r requirements.txt") from exc

        self._patch_blinkpy_oauth_signin(blink_api)
        session = ClientSession()
        blink = Blink(session=session)
        auth_data = self._load_auth_data()
        blink.auth = Auth(auth_data, no_prompt=True)
        try:
            started = await blink.start()
        except BlinkTwoFARequiredError as exc:
            await session.close()
            raise BlinkCameraError(
                "Blink requires two-factor verification. Complete verification and save "
                f"credentials to {settings.blink_auth_file}."
            ) from exc
        except Exception:
            await session.close()
            raise
        if not started:
            await session.close()
            raise BlinkCameraError("Blink login/setup failed. Check credentials, 2FA state, or Blink API logs.")
        self._blink = blink
        return blink

    def _load_auth_data(self) -> dict:
        auth_path = Path(settings.blink_auth_file)
        if auth_path.exists():
            try:
                data = json.loads(auth_path.read_text())
            except (OSError, json.JSONDecodeError) as exc:
                raise BlinkCameraError(f"Blink auth file could not be read: {auth_path}") from exc
            if isinstance(data, dict):
                return data
            raise BlinkCameraError(f"Blink auth file is not a JSON object: {auth_path}")

        return {
            "username": settings.blink_username,
            "password": settings.blink_password,
        }

    def _patch_blinkpy_oauth_signin(self, blink_api) -> None:
        """Patch blinkpy 0.25.6 OAuth logging bug for non-202 failures.

        blinkpy 0.25.6 references ``response_text`` before assignment when
        Blink returns statuses such as 429 rate limiting. This hides the real
        Blink error from the UI. Keep the same success/2FA behavior, but raise a
        useful error for rate limits and other OAuth failures.
        """
        if getattr(blink_api.oauth_signin, "_rebrewie_patched", False):
            return

        async def oauth_signin(auth, email, password, csrf_token):
            headers = {
                "User-Agent": blink_api.OAUTH_USER_AGENT,
                "Accept": "*/*",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://api.oauth.blink.com",
                "Referer": blink_api.OAUTH_SIGNIN_URL,
            }
            data = {
                "username": email,
                "password": password,
                "csrf-token": csrf_token,
            }
            response = await auth.session.post(
                blink_api.OAUTH_SIGNIN_URL, headers=headers, data=data, allow_redirects=False
            )
            response_text = await response.text()

            if response.status == 412:
                return "2FA_REQUIRED"

            if response.status == 202:
                try:
                    response_json = json.loads(response_text)
                except json.JSONDecodeError:
                    response_json = {}
                if (
                    response_json.get("tsv_state")
                    or response_json.get("tsv_methods")
                    or response_json.get("next_time_in_secs")
                ):
                    return "2FA_REQUIRED"

            if response.status in [301, 302, 303, 307, 308]:
                return "SUCCESS"

            try:
                error_json = json.loads(response_text)
            except json.JSONDecodeError:
                error_json = {}
            description = (
                error_json.get("error_description")
                or error_json.get("error")
                or response_text[:240]
                or "unknown Blink OAuth error"
            )
            wait_s = error_json.get("next_time_in_secs")
            if wait_s:
                description = f"{description} Try again in {wait_s} seconds."
            raise BlinkCameraError(f"Blink OAuth sign-in failed ({response.status}): {description}")

        oauth_signin._rebrewie_patched = True
        blink_api.oauth_signin = oauth_signin

    def _format_error(self, exc: Exception) -> str:
        msg = str(exc).strip()
        if msg:
            return msg
        return f"{type(exc).__module__}.{type(exc).__name__}"

    def _select_camera(self, cameras: dict):
        if not cameras:
            raise BlinkCameraError("No Blink cameras were found on this account")

        if settings.blink_camera_name:
            camera = cameras.get(settings.blink_camera_name)
            if camera is None:
                names = ", ".join(sorted(cameras.keys()))
                raise BlinkCameraError(
                    f"Blink camera {settings.blink_camera_name!r} was not found. Available: {names}"
                )
            return camera

        return next(iter(cameras.values()))


blink_camera_service = BlinkCameraService()
