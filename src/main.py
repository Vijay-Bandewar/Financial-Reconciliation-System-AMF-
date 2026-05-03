from __future__ import annotations

import argparse
from datetime import date
import hashlib
from pathlib import Path

import oracledb

from .config import load_settings
from .db import OracleConnInfo, connect, executemany, fetchall, call_proc
from .excel_ingest import read_external_excel
from .report_writer import write_run_report


def _file_checksum(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="AMF Reconciliation Pipeline")
    p.add_argument("--source", required=True, help="External source/system name (e.g., AMF)")
    p.add_argument("--run-date", required=True, help="Business date (YYYY-MM-DD)")
    p.add_argument("--input", required=True, help="Path to external Excel file")
    p.add_argument("--sheet", default=0, help="Sheet index/name for Excel", type=str)
    p.add_argument("--env", default=None, help="Optional path to .env")
    return p.parse_args()


def _coerce_sheet(sheet: str):
    # Allow "0" / "1" numeric or a literal sheet name.
    try:
        return int(sheet)
    except ValueError:
        return sheet


def _validate_sql_identifier(name: str) -> str:
    """
    Very small safety check since INTERNAL_TXN_SOURCE is interpolated into SQL.
    Allows schema-qualified identifiers like BANK.INTERNAL_TXN_VW.
    """
    n = name.strip()
    if not n:
        raise ValueError("INTERNAL_TXN_SOURCE is empty")
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.$#")
    if any(ch not in allowed for ch in n):
        raise ValueError(
            "INTERNAL_TXN_SOURCE contains unsupported characters. "
            "Use a simple table/view name like INTERNAL_TXN_VW or SCHEMA.INTERNAL_TXN_VW."
        )
    return n


def main() -> int:
    args = _parse_args()
    settings = load_settings(args.env)

    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(str(input_path))

    run_date = date.fromisoformat(args.run_date)
    checksum = _file_checksum(input_path)

    info = OracleConnInfo(
        user=settings.oracle_user,
        password=settings.oracle_password,
        dsn=settings.oracle_dsn,
    )
    conn = connect(info)
    try:
        conn.autocommit = False

        # 1) Create run
        with conn.cursor() as cur:
            run_id_var = cur.var(oracledb.NUMBER)
            cur.execute(
                """
                INSERT INTO recon_run (run_date, source_system, file_name, file_checksum, status, started_at)
                VALUES (:run_date, :source_system, :file_name, :file_checksum, 'STARTED', SYSTIMESTAMP)
                RETURNING run_id INTO :run_id
                """,
                dict(
                    run_date=run_date,
                    source_system=args.source,
                    file_name=input_path.name,
                    file_checksum=checksum,
                    run_id=run_id_var,
                ),
            )
            run_id = int(run_id_var.getvalue()[0])

        # 2) Read + load external transactions
        rows = read_external_excel(input_path, sheet_name=_coerce_sheet(args.sheet))
        executemany(
            conn,
            """
            INSERT INTO txn_canonical_ext
              (run_id, source_row_num, txn_date, amount, currency, reference, account, narration, counterparty, row_hash)
            VALUES
              (:1, :2, :3, :4, :5, :6, :7, :8, :9, :10)
            """,
            (
                (
                    run_id,
                    r.source_row_num,
                    r.txn_date,
                    r.amount,
                    r.currency,
                    r.reference,
                    r.account,
                    r.narration,
                    r.counterparty,
                    r.row_hash,
                )
                for r in rows
            ),
        )

        # 3) Reconcile (PL/SQL)
        call_proc(conn, "recon_pkg.run_reconciliation", [run_id, settings.internal_txn_source])

        internal_source = _validate_sql_identifier(settings.internal_txn_source)

        # 4) Pull summary + breaks + matches for the Excel output
        summary_rows = fetchall(
            conn,
            """
            SELECT
              m.run_id,
              r.run_date,
              r.source_system,
              m.ext_total_count,
              m.ext_total_amount,
              m.int_total_count,
              m.int_total_amount,
              m.matched_count,
              m.matched_amount,
              m.break_count,
              m.break_amount,
              CASE WHEN m.ext_total_count = 0 THEN 0 ELSE m.matched_count / m.ext_total_count END AS match_rate
            FROM recon_metrics m
            JOIN recon_run r ON r.run_id = m.run_id
            WHERE m.run_id = :run_id
            """,
            {"run_id": run_id},
        )
        if not summary_rows:
            raise RuntimeError(f"No recon_metrics row created for run_id={run_id}")

        cols = [
            "run_id",
            "run_date",
            "source_system",
            "ext_total_count",
            "ext_total_amount",
            "int_total_count",
            "int_total_amount",
            "matched_count",
            "matched_amount",
            "break_count",
            "break_amount",
            "match_rate",
        ]
        run_summary = dict(zip(cols, summary_rows[0]))

        breaks = fetchall(
            conn,
            """
            SELECT
              break_code,
              break_reason,
              ext_txn_id,
              int_txn_id,
              amount,
              txn_date,
              reference,
              account
            FROM recon_break
            WHERE run_id = :run_id
            ORDER BY break_code, txn_date
            """,
            {"run_id": run_id},
        )
        break_cols = ["break_code", "break_reason", "ext_txn_id", "int_txn_id", "amount", "txn_date", "reference", "account"]
        breaks_rows = [dict(zip(break_cols, b)) for b in breaks]

        matched = fetchall(
            conn,
            f"""
            SELECT
              m.match_type,
              m.match_score,
              e.ext_txn_id,
              i.int_txn_id,
              e.txn_date,
              e.amount,
              e.currency,
              e.reference,
              e.account
            FROM recon_match m
            JOIN txn_canonical_ext e
              ON e.ext_txn_id = m.ext_txn_id
            JOIN {internal_source} i
              ON i.int_txn_id = m.int_txn_id
            WHERE m.run_id = :run_id
            ORDER BY e.txn_date, e.amount DESC
            """,
            {"run_id": run_id},
        )
        matched_cols = [
            "match_type",
            "match_score",
            "ext_txn_id",
            "int_txn_id",
            "txn_date",
            "amount",
            "currency",
            "reference",
            "account",
        ]
        matched_rows = [dict(zip(matched_cols, r)) for r in matched]

        break_counts = fetchall(
            conn,
            """
            SELECT break_code, COUNT(*) AS break_count, NVL(SUM(amount),0) AS break_amount
            FROM recon_break
            WHERE run_id = :run_id
            GROUP BY break_code
            ORDER BY break_code
            """,
            {"run_id": run_id},
        )
        break_counts_rows = [
            dict(zip(["break_code", "break_count", "break_amount"], r)) for r in break_counts
        ]

        # 5) Write output workbook
        output_dir = settings.output_dir
        output_path = output_dir / f"recon_{args.source}_{run_date.isoformat()}_run{run_id}.xlsx"
        write_run_report(
            output_path=output_path,
            run_summary=run_summary,
            breaks_rows=breaks_rows,
            matched_rows=matched_rows,
            break_counts_rows=break_counts_rows,
            discrepancy_highlight_amount=settings.discrepancy_highlight_amount,
        )

        # 6) Mark run complete
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE recon_run SET status='COMPLETED', ended_at=SYSTIMESTAMP WHERE run_id=:run_id",
                {"run_id": run_id},
            )

        conn.commit()
        print(f"Wrote {output_path}")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
