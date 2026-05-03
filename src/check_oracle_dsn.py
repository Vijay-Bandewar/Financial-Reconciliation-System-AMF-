"""Resolve ORACLE_DSN hostname only (no DB login). Run from repo root."""

from __future__ import annotations

import argparse
import socket
import sys

from .config import load_settings
from .db import dsn_host_hint


def main() -> int:
    p = argparse.ArgumentParser(description="Check that ORACLE_DSN host resolves (DNS).")
    p.add_argument("--env", default=None, help="Optional path to .env")
    args = p.parse_args()

    s = load_settings(args.env)
    host = dsn_host_hint(s.oracle_dsn)
    print(f"Host segment used for DNS check: {host!r}")

    if host.startswith("("):
        print("Cannot auto-check TNS-style DSN. Use Easy Connect (host:port/service) to test DNS.")
        return 0

    try:
        socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        print(f"FAIL: hostname does not resolve: {e}")
        return 1

    print("OK: hostname resolves.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
