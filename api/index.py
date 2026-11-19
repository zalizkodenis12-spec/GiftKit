"""Vercel Serverless ASGI entrypoint exporting FastAPI `app` from `backend.main`."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure project root is on sys.path for `backend.*` imports in Vercel Serverless
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Ensure serverless flags are set when loaded through api/index.py on Vercel
if os.environ.get("VERCEL"):
    os.environ.setdefault("DATABASE_PATH", "/tmp/giftkit.db")

from backend.main import app  # noqa: E402, F401
