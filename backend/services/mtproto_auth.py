"""Official Telegram MTProto (Telethon) auto-refresher for MRKT & Tonnel Mini App initData."""

from __future__ import annotations

import asyncio
import urllib.parse
from pathlib import Path
from typing import Any

from loguru import logger

from backend.config import IS_VERCEL, runtime_config
from backend.database import db

try:
    from telethon import TelegramClient, functions, types
    from telethon.errors import SessionPasswordNeededError
    from telethon.sessions import StringSession

    TELETHON_AVAILABLE = True
except Exception:
    TELETHON_AVAILABLE = False


class MtprotoAuthService:
    """Manages official Telegram user session to auto-fetch fresh MRKT & Tonnel WebApp initData."""

    def __init__(self) -> None:
        self._client: Any | None = None
        self._lock = asyncio.Lock()
        self._pending_phone: str = ""
        self._pending_phone_hash: str = ""
        self.is_authorized: bool = False
        self.account_label: str = ""
        self.last_refresh_at: str = ""
        self.last_error: str = ""

    @staticmethod
    def _session_path() -> Path:
        project_root = Path(__file__).resolve().parent.parent.parent
        data_dir = project_root / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir / "giftkit_mtproto"

    @staticmethod
    def _persist_env_values(updates: dict[str, str]) -> None:
        if IS_VERCEL:
            return
        try:
            env_path = Path(__file__).resolve().parent.parent.parent / ".env"
            lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
            for key, val in updates.items():
                if not val:
                    continue
                found = False
                for idx, line in enumerate(lines):
                    if line.startswith(f"{key}="):
                        lines[idx] = f"{key}={val}"
                        found = True
                        break
                if not found:
                    lines.append(f"{key}={val}")
            env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except Exception as exc:
            logger.debug(f"mtproto _persist_env_values skipped: {exc}")

    def has_api_credentials(self) -> bool:
        return bool(TELETHON_AVAILABLE and runtime_config.tg_api_id > 0 and runtime_config.tg_api_hash)

    async def _ensure_connected(self) -> Any | None:
        if not self.has_api_credentials():
            return None
        if self._client is None:
            session_str = runtime_config.tg_session_string
            if session_str:
                session_arg: Any = StringSession(session_str)
            else:
                session_arg = str(self._session_path())
            self._client = TelegramClient(
                session_arg,
                runtime_config.tg_api_id,
                runtime_config.tg_api_hash,
                device_model="PC 64bit",
                system_version="Windows 10",
                app_version="5.10.0",
                lang_code="en",
                system_lang_code="en-US",
            )
        if not self._client.is_connected():
            await self._client.connect()
        try:
            self.is_authorized = bool(await self._client.is_user_authorized())
            if self.is_authorized and not self.account_label:
                me = await self._client.get_me()
                if me:
                    uname = f"@{me.username}" if getattr(me, "username", None) else str(me.id)
                    fname = str(getattr(me, "first_name", "") or "").strip()
                    self.account_label = f"{fname} ({uname})".strip()
        except Exception as exc:
            self.last_error = str(exc)
            self.is_authorized = False
        return self._client

    async def startup(self) -> None:
        """Check if a saved Telethon session already exists and refresh MRKT/Tonnel tokens."""
        if IS_VERCEL or not self.has_api_credentials():
            return
        session_file = Path(f"{self._session_path()}.session")
        if not runtime_config.tg_session_string and not session_file.exists():
            logger.info("MTProto API_ID/API_HASH ready; waiting for one-time Telegram login to auto-refresh MRKT & Tonnel.")
            return
        try:
            client = await self._ensure_connected()
            if client and self.is_authorized:
                logger.info(f"MTProto session active for {self.account_label}. Refreshing MRKT & Tonnel initData...")
                await self.refresh_all_init_data()
        except Exception as exc:
            self.last_error = str(exc)
            logger.warning(f"MTProto startup skipped: {exc}")

    async def shutdown(self) -> None:
        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception:
                pass
            self._client = None

    async def send_login_code(self, phone: str) -> dict[str, Any]:
        """Step 1 of one-time Telegram MTProto login: sends official login code to Telegram app."""
        clean_phone = (phone or "").strip().replace(" ", "")
        if not clean_phone:
            return {"ok": False, "error": "Вкажіть номер телефону у форматі +380..."}
        if not self.has_api_credentials():
            return {"ok": False, "error": "TG_API_ID або TG_API_HASH не налаштовані"}

        async with self._lock:
            try:
                client = await self._ensure_connected()
                if not client:
                    return {"ok": False, "error": "Не вдалося підключитися до Telegram MTProto"}
                if await client.is_user_authorized():
                    self.is_authorized = True
                    res = await self.refresh_all_init_data()
                    return {"ok": True, "already_authorized": True, "account": self.account_label, "refresh": res}
                sent = await client.send_code_request(clean_phone)
                self._pending_phone = clean_phone
                self._pending_phone_hash = sent.phone_code_hash
                self.last_error = ""
                return {"ok": True, "code_sent": True, "phone": clean_phone}
            except Exception as exc:
                self.last_error = str(exc)
                return {"ok": False, "error": str(exc)}

    async def verify_login_code(self, code: str, password: str = "", phone: str = "") -> dict[str, Any]:
        """Step 2 of one-time Telegram MTProto login: confirms code (and optional 2FA password)."""
        clean_code = (code or "").strip().replace(" ", "").replace("-", "")
        target_phone = (phone or self._pending_phone or "").strip().replace(" ", "")
        if not target_phone or not clean_code:
            return {"ok": False, "error": "Введіть код із Telegram"}

        async with self._lock:
            try:
                client = await self._ensure_connected()
                if not client:
                    return {"ok": False, "error": "Клієнт MTProto не підключений"}
                try:
                    await client.sign_in(
                        phone=target_phone,
                        code=clean_code,
                        phone_code_hash=self._pending_phone_hash or None,
                    )
                except SessionPasswordNeededError:
                    if not (password or "").strip():
                        return {
                            "ok": False,
                            "needs_password": True,
                            "error": "На акаунті увімкнено хмарний пароль (2FA) — введіть його.",
                        }
                    await client.sign_in(password=password.strip())

                self.is_authorized = bool(await client.is_user_authorized())
                me = await client.get_me()
                if me:
                    uname = f"@{me.username}" if getattr(me, "username", None) else str(me.id)
                    fname = str(getattr(me, "first_name", "") or "").strip()
                    self.account_label = f"{fname} ({uname})".strip()
                self.last_error = ""
            except Exception as exc:
                self.last_error = str(exc)
                return {"ok": False, "error": str(exc)}

        refresh_res = await self.refresh_all_init_data()
        return {
            "ok": True,
            "authorized": self.is_authorized,
            "account": self.account_label,
            "refresh": refresh_res,
        }

    @staticmethod
    def _extract_init_data_from_webview_url(url: str) -> str:
        """Extract decoded tgWebAppData parameter from Telegram WebView URL fragment."""
        if not url or "tgWebAppData=" not in url:
            return ""
        parsed = urllib.parse.urlparse(url)
        frag_params = urllib.parse.parse_qs(parsed.fragment)
        raw_list = frag_params.get("tgWebAppData")
        if raw_list and raw_list[0]:
            return urllib.parse.unquote(raw_list[0]).strip()
        q_params = urllib.parse.parse_qs(parsed.query)
        raw_q = q_params.get("tgWebAppData")
        if raw_q and raw_q[0]:
            return urllib.parse.unquote(raw_q[0]).strip()
        return ""

    async def _fetch_bot_init_data(
        self,
        bot_username: str,
        app_short_name: str,
        fallback_url: str,
    ) -> str:
        client = await self._ensure_connected()
        if not client or not self.is_authorized:
            return ""

        bot_entity = await client.get_input_entity(bot_username)

        # Method 1: RequestAppWebViewRequest (official Direct Mini App endpoint)
        try:
            res = await client(
                functions.messages.RequestAppWebViewRequest(
                    peer=bot_entity,
                    app=types.InputBotAppShortName(bot_id=bot_entity, short_name=app_short_name),
                    platform="android",
                    write_allowed=True,
                )
            )
            init_data = self._extract_init_data_from_webview_url(getattr(res, "url", "") or "")
            if init_data:
                return init_data
        except Exception as exc:
            logger.debug(f"RequestAppWebView({bot_username}/{app_short_name}) fallback: {exc}")

        # Method 2: RequestWebViewRequest (standard bot webview)
        try:
            res = await client(
                functions.messages.RequestWebViewRequest(
                    peer=bot_entity,
                    bot=bot_entity,
                    platform="android",
                    url=fallback_url,
                    from_bot_menu=True,
                )
            )
            init_data = self._extract_init_data_from_webview_url(getattr(res, "url", "") or "")
            if init_data:
                return init_data
        except Exception as exc:
            logger.debug(f"RequestWebView({bot_username}) error: {exc}")

        return ""

    async def refresh_mrkt_init_data(self) -> bool:
        if not self.has_api_credentials():
            return False
        async with self._lock:
            try:
                init_data = await self._fetch_bot_init_data("mrkt", "app", "https://cdn.tgmrkt.io")
                if init_data:
                    runtime_config.apply_overrides({"mrkt_init_data": init_data})
                    await db.set_setting("mrkt_init_data", init_data)
                    self._persist_env_values({"MRKT_INIT_DATA": init_data})
                    logger.info("MTProto refreshed live MRKT initData successfully.")
                    return True
            except Exception as exc:
                self.last_error = f"MRKT refresh: {exc}"
                logger.warning(f"MTProto MRKT refresh failed: {exc}")
        return False

    async def refresh_tonnel_init_data(self) -> bool:
        if not self.has_api_credentials():
            return False
        async with self._lock:
            try:
                init_data = await self._fetch_bot_init_data(
                    "tonnel_network_bot",
                    "gifts",
                    "https://market.tonnel.network",
                )
                if init_data:
                    runtime_config.apply_overrides({"tonnel_init_data": init_data})
                    await db.set_setting("tonnel_init_data", init_data)
                    self._persist_env_values({"TONNEL_INIT_DATA": init_data})
                    logger.info("MTProto refreshed live Tonnel initData successfully.")
                    return True
            except Exception as exc:
                self.last_error = f"Tonnel refresh: {exc}"
                logger.warning(f"MTProto Tonnel refresh failed: {exc}")
        return False

    async def refresh_all_init_data(self) -> dict[str, Any]:
        mrkt_ok = await self.refresh_mrkt_init_data()
        tonnel_ok = await self.refresh_tonnel_init_data()
        if mrkt_ok or tonnel_ok:
            from backend.database import utc_now_iso

            self.last_refresh_at = utc_now_iso()
        return {
            "mrkt_refreshed": mrkt_ok,
            "tonnel_refreshed": tonnel_ok,
            "last_refresh_at": self.last_refresh_at,
        }

    def get_status(self) -> dict[str, Any]:
        return {
            "telethon_available": TELETHON_AVAILABLE,
            "has_api_credentials": self.has_api_credentials(),
            "authorized": self.is_authorized,
            "account": self.account_label,
            "has_mrkt_init_data": bool(runtime_config.mrkt_init_data),
            "has_tonnel_init_data": bool(runtime_config.tonnel_init_data),
            "last_refresh_at": self.last_refresh_at,
            "last_error": self.last_error,
            "is_vercel": IS_VERCEL,
        }


mtproto_auth = MtprotoAuthService()
