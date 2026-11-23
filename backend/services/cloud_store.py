"""Persistent Cloud KV Store (Upstash Redis / Vercel KV REST API) for 24/7 serverless state."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
from loguru import logger

from backend.config import base_settings


class CloudStore:
    """Zero-dependency REST client for Upstash Redis / Vercel KV.

    When KV_REST_API_URL + KV_REST_API_TOKEN (or UPSTASH_REDIS_REST_URL + UPSTASH_REDIS_REST_TOKEN)
    are configured in Vercel Environment Variables, user sniper rules, portfolio, offers, profile,
    market tokens, MRKT snapshots, and deduped alert keys persist 24/7 across all Vercel cold starts.
    """

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    @staticmethod
    def _credentials() -> tuple[str, str]:
        url = (
            os.environ.get("KV_REST_API_URL")
            or os.environ.get("UPSTASH_REDIS_REST_URL")
            or base_settings.KV_REST_API_URL
            or base_settings.UPSTASH_REDIS_REST_URL
            or ""
        ).strip().rstrip("/")
        token = (
            os.environ.get("KV_REST_API_TOKEN")
            or os.environ.get("UPSTASH_REDIS_REST_TOKEN")
            or base_settings.KV_REST_API_TOKEN
            or base_settings.UPSTASH_REDIS_REST_TOKEN
            or ""
        ).strip()
        return url, token

    @property
    def is_configured(self) -> bool:
        url, token = self._credentials()
        return bool(url.startswith("https://") and token)

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=2.5))
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _command(self, *parts: Any) -> Any | None:
        url, token = self._credentials()
        if not url or not token:
            return None
        try:
            client = self._get_client()
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=list(parts),
            )
            if resp.status_code == 200:
                body = resp.json()
                return body.get("result") if isinstance(body, dict) else body
            logger.debug(f"CloudStore HTTP {resp.status_code}: {resp.text[:120]}")
        except Exception as exc:
            logger.debug(f"CloudStore error: {exc}")
        return None

    async def set_json(self, key: str, value: Any, ttl_seconds: int | None = None) -> bool:
        if not self.is_configured:
            return False
        raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        if ttl_seconds and ttl_seconds > 0:
            res = await self._command("SET", key, raw, "EX", int(ttl_seconds))
        else:
            res = await self._command("SET", key, raw)
        return res is not None

    async def get_json(self, key: str) -> Any | None:
        if not self.is_configured:
            return None
        raw = await self._command("GET", key)
        if not isinstance(raw, str) or not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    async def save_user_state(self, user_id: str, envelope: dict[str, Any]) -> bool:
        uid = str(user_id or "").strip()
        if not uid or not self.is_configured:
            return False
        ok = await self.set_json(f"giftkit:user:{uid}:state", envelope)
        if ok:
            await self._command("SADD", "giftkit:active_users", uid)
        return ok

    async def load_user_state(self, user_id: str) -> dict[str, Any] | None:
        uid = str(user_id or "").strip()
        if not uid or not self.is_configured:
            return None
        val = await self.get_json(f"giftkit:user:{uid}:state")
        return val if isinstance(val, dict) else None

    async def list_active_users(self) -> list[str]:
        if not self.is_configured:
            return []
        res = await self._command("SMEMBERS", "giftkit:active_users")
        if isinstance(res, list):
            return [str(x).strip() for x in res if str(x).strip()]
        return []

    async def save_market_credentials(self, creds: dict[str, str]) -> bool:
        if not self.is_configured or not creds:
            return False
        existing = await self.get_json("giftkit:market_creds")
        merged = {**(existing if isinstance(existing, dict) else {}), **{k: v for k, v in creds.items() if v}}
        return await self.set_json("giftkit:market_creds", merged)

    async def load_market_credentials(self) -> dict[str, str]:
        val = await self.get_json("giftkit:market_creds")
        return val if isinstance(val, dict) else {}

    async def save_mrkt_snapshot(self, snapshot: dict[str, Any]) -> bool:
        if not self.is_configured or not snapshot:
            return False
        return await self.set_json("giftkit:mrkt_snapshot", snapshot, ttl_seconds=7200)

    async def load_mrkt_snapshot(self) -> dict[str, Any] | None:
        val = await self.get_json("giftkit:mrkt_snapshot")
        return val if isinstance(val, dict) else None

    async def mark_alert_seen(self, dedup_key: str, ttl_seconds: int = 86400 * 3) -> bool:
        if not self.is_configured:
            return False
        res = await self._command("SET", f"giftkit:seen:{dedup_key}", "1", "EX", int(ttl_seconds), "NX")
        return res == "OK"

    async def is_alert_seen(self, dedup_key: str) -> bool:
        if not self.is_configured:
            return False
        res = await self._command("EXISTS", f"giftkit:seen:{dedup_key}")
        return bool(res)


cloud_store = CloudStore()
