from __future__ import annotations

from .config import load_settings
from .db import OracleConnInfo, connect, fetchall


def main() -> int:
    s = load_settings()
    conn = connect(OracleConnInfo(s.oracle_user, s.oracle_password, s.oracle_dsn))
    try:
        rows = fetchall(conn, "SELECT 'OK' FROM dual")
        print(rows[0][0])

        objs = fetchall(
            conn,
            """
            SELECT object_type, object_name
            FROM user_objects
            WHERE object_name IN ('RECON_RUN','TXN_CANONICAL_EXT','RECON_PKG')
            ORDER BY object_type, object_name
            """,
        )
        for t, n in objs:
            print(f"{t}: {n}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
