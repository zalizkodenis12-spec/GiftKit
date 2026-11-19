"""Auto-reconnecting stable HTTPS tunnel keeper using Serveo (no 5-min domain rotation)."""

from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path

import httpx

LOCAL_API = "http://127.0.0.1:8000"
KEY_PATH = Path(__file__).resolve().parent / "bin" / "giftkit_tunnel_key"
SERVEO_RE = re.compile(r"https://[a-zA-Z0-9.-]+\.serveousercontent\.com")


def ensure_ssh_key() -> None:
    KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not KEY_PATH.exists():
        subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-N", "", "-f", str(KEY_PATH)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def sync_webapp_url(url: str) -> None:
    try:
        r = httpx.patch(f"{LOCAL_API}/api/settings", json={"webapp_url": url}, timeout=8)
        print(f"[TUNNEL KEEPER] Synced GiftKit Mini App URL -> {url} (HTTP {r.status_code})", flush=True)
    except Exception as exc:
        print(f"[TUNNEL KEEPER] Sync error: {exc}", flush=True)


def main() -> None:
    ensure_ssh_key()
    last_url = ""
    while True:
        print("[TUNNEL KEEPER] Starting stable SSH tunnel via serveo.net...", flush=True)
        proc = subprocess.Popen(
            [
                "ssh",
                "-i", str(KEY_PATH),
                "-o", "StrictHostKeyChecking=no",
                "-o", "ServerAliveInterval=20",
                "-o", "ServerAliveCountMax=3",
                "-o", "ConnectTimeout=10",
                "-R", "80:127.0.0.1:8000",
                "serveo.net",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            m = SERVEO_RE.search(line)
            if m:
                url = m.group(0)
                if url != last_url:
                    last_url = url
                    sync_webapp_url(url)
        proc.wait()
        print("[TUNNEL KEEPER] Serveo connection ended — reconnecting in 2s...", flush=True)
        time.sleep(2)


if __name__ == "__main__":
    main()
