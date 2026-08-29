"""Entry point for the PyInstaller-packaged desktop backend.

The dev path launches the backend as ``python -m uvicorn app.main:app``; the
packaged binary runs this instead, driving the same ASGI app through uvicorn
without needing a system Python. It accepts the same ``--host`` / ``--port``
arguments ``main.js`` passes in either mode.
"""
from __future__ import annotations

import argparse

import uvicorn

from app.main import app


def main() -> int:
    parser = argparse.ArgumentParser(prog="reqmesh-backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
