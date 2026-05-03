from __future__ import annotations

from dataclasses import dataclass
import socket
from typing import Any, Iterable, Sequence

import oracledb


@dataclass(frozen=True)
class OracleConnInfo:
    user: str
    password: str
    dsn: str


def dsn_host_hint(dsn: str) -> str:
    """Best-effort host part for error messages (Easy Connect: host:port/service)."""
    s = dsn.strip()
    u = s.upper()
    if u.startswith("(DESCRIPTION"):
        return "(TNS-style DSN — hostname is not in a simple host:port form)"
    if ":" in s:
        return s.split(":", 1)[0].strip() or s
    return s


def connect(info: OracleConnInfo) -> oracledb.Connection:
    # oracledb defaults to Thin mode which is easiest on Windows.
    try:
        return oracledb.connect(user=info.user, password=info.password, dsn=info.dsn)
    except socket.gaierror as e:
        host = dsn_host_hint(info.dsn)
        raise ConnectionError(
            "Oracle connection failed: the hostname in ORACLE_DSN could not be resolved "
            f"(getaddrinfo). Host part used for DNS: {host!r}. "
            "Fix ORACLE_DSN to Easy Connect form host:port/service_name "
            "(e.g. localhost:1521/XEPDB1), fix typos, connect VPN if required, "
            "or use the machine IP instead of an internal DNS name."
        ) from e


def executemany(
    conn: oracledb.Connection,
    sql: str,
    rows: Iterable[Sequence[Any]],
    *,
    batcherrors: bool = True,
) -> None:
    with conn.cursor() as cur:
        cur.executemany(sql, list(rows), batcherrors=batcherrors)


def fetchall(conn: oracledb.Connection, sql: str, params: dict[str, Any] | None = None) -> list[tuple[Any, ...]]:
    with conn.cursor() as cur:
        cur.execute(sql, params or {})
        return cur.fetchall()


def call_proc(conn: oracledb.Connection, proc_name: str, params: list[Any]) -> None:
    with conn.cursor() as cur:
        cur.callproc(proc_name, params)
