"""Cryptographic HMAC-SHA256 Authentication & Cross-Device State Sync Service for GiftKit."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import urllib.parse
from typing import Any

from backend.config import base_settings, runtime_config

DEFAULT_ADMIN_USER_ID = runtime_config.tg_admin_chat_id.strip() or base_settings.TG_ADMIN_CHAT_ID.strip() or "owner"


def _get_signing_secret() -> bytes:
    """Derive deterministic HMAC-SHA256 signing secret from TG_BOT_TOKEN or local fallback."""
    raw = (
        runtime_config.tg_bot_token.strip()
        or base_settings.TG_BOT_TOKEN.strip()
        or "giftkit-local-secret-key"
    )
    return hashlib.sha256(f"giftkit-hmac-v1:{raw}".encode("utf-8")).digest()


def get_bot_sync_signature() -> str:
    """Compute HMAC header signature for internal bot <-> Vercel synchronization."""
    secret = _get_signing_secret()
    return hmac.new(secret, b"giftkit-internal-bot-sync", hashlib.sha256).hexdigest()


def verify_bot_sync_signature(signature: str) -> bool:
    if not signature:
        return False
    expected = get_bot_sync_signature()
    return hmac.compare_digest(expected, signature.strip())


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(text: str) -> bytes:
    padded = text + "=" * ((4 - len(text) % 4) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def normalize_user_dict(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a Telegram user object into canonical GiftKit user dict."""
    tg_user_id = str(raw.get("tg_user_id") or raw.get("id") or "").strip()
    username = str(raw.get("username") or "").strip().lstrip("@")
    first_name = str(raw.get("first_name") or "").strip()
    last_name = str(raw.get("last_name") or "").strip()
    photo_url = str(raw.get("photo_url") or "").strip()
    if not photo_url and username:
        photo_url = f"https://t.me/i/userpic/320/{username}.jpg"
    return {
        "tg_user_id": tg_user_id,
        "username": username,
        "first_name": first_name,
        "last_name": last_name,
        "photo_url": photo_url,
    }


def verify_telegram_init_data(init_data_raw: str) -> dict[str, Any] | None:
    """Validate Telegram Mini App initData query string using standard Telegram HMAC-SHA256."""
    raw = (init_data_raw or "").strip()
    if not raw:
        return None

    try:
        pairs = urllib.parse.parse_qsl(raw, keep_blank_values=True)
    except Exception:
        return None

    if not pairs:
        return None

    received_hash = ""
    user_json_str = ""
    check_items: list[str] = []

    for k, v in pairs:
        if k == "hash":
            received_hash = v.strip().lower()
        else:
            check_items.append(f"{k}={v}")
            if k == "user":
                user_json_str = v

    if not received_hash or not user_json_str:
        return None

    check_items.sort()
    data_check_string = "\n".join(check_items)

    bot_token = (runtime_config.tg_bot_token or base_settings.TG_BOT_TOKEN).strip()
    token_for_hmac = bot_token if bot_token else "giftkit-local-secret-key"

    secret_key = hmac.new(
        b"WebAppData",
        token_for_hmac.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    computed_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest().lower()

    if not hmac.compare_digest(computed_hash, received_hash):
        return None

    try:
        user_obj = json.loads(user_json_str)
    except Exception:
        return None

    if not isinstance(user_obj, dict) or not user_obj.get("id"):
        return None

    return normalize_user_dict(user_obj)


def create_signed_token(user_dict: dict[str, Any], ttl_seconds: int = 86400 * 30) -> str:
    """Create a URL-safe base64 JSON session token signed with HMAC-SHA256."""
    norm = normalize_user_dict(user_dict)
    if not norm["tg_user_id"]:
        raise ValueError("tg_user_id is required to create a signed token")
    token_photo = norm["photo_url"] if len(norm["photo_url"]) <= 512 else ""
    payload = {
        **norm,
        "photo_url": token_photo,
        "exp": int(time.time()) + int(ttl_seconds),
    }
    raw_bytes = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    b64_payload = _b64url_encode(raw_bytes)
    sig = hmac.new(_get_signing_secret(), b64_payload.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{b64_payload}.{sig}"


def verify_signed_token(token: str) -> dict[str, Any] | None:
    """Verify HMAC signature and expiration of a session token; return user_dict or None."""
    raw = (token or "").strip()
    if not raw or "." not in raw:
        return None
    b64_payload, sig = raw.rsplit(".", 1)
    if not b64_payload or not sig:
        return None

    expected_sig = hmac.new(
        _get_signing_secret(),
        b64_payload.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected_sig, sig.lower()):
        return None

    try:
        payload = json.loads(_b64url_decode(b64_payload).decode("utf-8"))
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None

    exp = int(payload.get("exp") or 0)
    if exp < int(time.time()):
        return None

    norm = normalize_user_dict(payload)
    if not norm["tg_user_id"]:
        return None
    return norm


def _canonicalize_state_payload(user_id: str, state_payload: dict[str, Any]) -> dict[str, Any]:
    """Build deterministic canonical dictionary for HMAC state signing."""
    def _clean_int_list(items: Any) -> list[int]:
        res: set[int] = set()
        for x in items or []:
            try:
                res.add(int(x))
            except (TypeError, ValueError):
                pass
        return sorted(res)

    uid = str(user_id).strip()
    raw_prof = state_payload.get("user_profile")
    if isinstance(raw_prof, dict):
        user_profile = normalize_user_dict({**raw_prof, "tg_user_id": uid})
    else:
        user_profile = None

    out: dict[str, Any] = {
        "user_id": uid,
        "state_version": int(state_payload.get("state_version") or 1),
        "rules": list(state_payload.get("rules") or []),
        "offers": list(state_payload.get("offers") or []),
        "portfolio": list(state_payload.get("portfolio") or []),
        "deleted_rule_ids": _clean_int_list(state_payload.get("deleted_rule_ids")),
        "deleted_offer_ids": _clean_int_list(state_payload.get("deleted_offer_ids")),
        "deleted_portfolio_ids": _clean_int_list(state_payload.get("deleted_portfolio_ids")),
    }
    if user_profile is not None:
        out["user_profile"] = user_profile
    return out


def sign_state_envelope(user_id: str, state_payload: dict[str, Any]) -> dict[str, Any]:
    """Sign user's cross-device state snapshot with HMAC-SHA256 tied to user_id."""
    canonical = _canonicalize_state_payload(user_id, state_payload)
    serialized = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    signature = hmac.new(_get_signing_secret(), serialized, hashlib.sha256).hexdigest()
    return {
        **canonical,
        "signature": signature,
    }


def verify_state_envelope(user_id: str, envelope: dict[str, Any]) -> dict[str, Any] | None:
    """Verify HMAC-SHA256 signature of a cross-device state snapshot tied to user_id."""
    if not isinstance(envelope, dict):
        return None
    env_user_id = str(envelope.get("user_id") or "").strip()
    target_user_id = str(user_id).strip()
    if not env_user_id or env_user_id != target_user_id:
        return None

    received_sig = str(envelope.get("signature") or "").strip().lower()
    if not received_sig:
        return None

    canonical = _canonicalize_state_payload(target_user_id, envelope)
    serialized = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    expected_sig = hmac.new(_get_signing_secret(), serialized, hashlib.sha256).hexdigest().lower()

    if not hmac.compare_digest(expected_sig, received_sig):
        return None
    return canonical


# -------------------- DEVICE LOGIN NONCE STORE --------------------

_LOGIN_NONCES: dict[str, dict[str, Any]] = {}
_NONCE_TTL_SECONDS = 900  # 15 minutes


def _cleanup_expired_nonces() -> None:
    now = time.time()
    expired = [k for k, v in _LOGIN_NONCES.items() if now - float(v.get("created_at", 0)) > _NONCE_TTL_SECONDS]
    for k in expired:
        _LOGIN_NONCES.pop(k, None)


def create_login_nonce() -> str:
    """Generate a one-time login nonce for 1-click Telegram Bot login from browser/PWA."""
    _cleanup_expired_nonces()
    nonce = secrets.token_urlsafe(16)
    _LOGIN_NONCES[nonce] = {
        "created_at": time.time(),
        "user": None,
    }
    return nonce


def approve_login_nonce(nonce: str, user_dict: dict[str, Any]) -> bool:
    """Approve a login nonce when the user taps /start login_<nonce> in @GiftKit_bot."""
    _cleanup_expired_nonces()
    clean_nonce = (nonce or "").strip()
    if not clean_nonce:
        return False
    norm = normalize_user_dict(user_dict)
    if not norm["tg_user_id"]:
        return False
    _LOGIN_NONCES[clean_nonce] = {
        "created_at": time.time(),
        "user": norm,
    }
    return True


def poll_login_nonce(nonce: str) -> dict[str, Any] | None:
    """Return approved user_dict for a login nonce if ready, else None."""
    _cleanup_expired_nonces()
    clean_nonce = (nonce or "").strip()
    entry = _LOGIN_NONCES.get(clean_nonce)
    if not entry:
        return None
    user = entry.get("user")
    if isinstance(user, dict) and user.get("tg_user_id"):
        return dict(user)
    return None
