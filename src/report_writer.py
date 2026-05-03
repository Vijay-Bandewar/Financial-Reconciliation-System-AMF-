from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def write_run_report(
    *,
    output_path: str | Path,
    run_summary: dict[str, Any],
    breaks_rows: list[dict[str, Any]],
    matched_rows: list[dict[str, Any]],
    break_counts_rows: list[dict[str, Any]],
    discrepancy_highlight_amount: float = 100000.0,
) -> Path:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    df_breaks = pd.DataFrame(breaks_rows)
    df_matches = pd.DataFrame(matched_rows)
    df_break_counts = pd.DataFrame(break_counts_rows)
    df_summary = pd.DataFrame([run_summary])

    with pd.ExcelWriter(out, engine="xlsxwriter") as writer:
        # Raw data tabs (useful for audit)
        df_summary.to_excel(writer, sheet_name="Summary Data", index=False)
        df_matches.to_excel(writer, sheet_name="Matched Transactions", index=False)
        df_breaks.to_excel(writer, sheet_name="Discrepancy Alert", index=False)
        df_break_counts.to_excel(writer, sheet_name="Break Counts", index=False)

        wb = writer.book
        fmt_header = wb.add_format({"bold": True, "bg_color": "#1F4E79", "font_color": "white"})
        fmt_title = wb.add_format({"bold": True, "font_size": 16, "font_color": "#1F4E79"})
        fmt_label = wb.add_format({"bold": True, "font_color": "#333333"})
        fmt_kpi = wb.add_format({"bold": True, "font_size": 14})
        fmt_pct = wb.add_format({"num_format": "0.00%"})
        fmt_money = wb.add_format({"num_format": "#,##0.00"})
        fmt_highlight = wb.add_format({"bg_color": "#FFC7CE", "font_color": "#9C0006"})
        fmt_warn = wb.add_format({"bg_color": "#FFEB9C", "font_color": "#9C6500"})

        def _style_table(sheet_name: str, df: pd.DataFrame, *, money_cols: tuple[str, ...] = (), pct_cols: tuple[str, ...] = ()):
            ws = writer.sheets[sheet_name]
            ws.set_row(0, None, fmt_header)
            ws.freeze_panes(1, 0)
            ws.autofilter(0, 0, max(0, df.shape[0]), max(0, df.shape[1] - 1))
            ws.set_column(0, max(0, df.shape[1] - 1), 22)
            for c in money_cols:
                if c in df.columns:
                    col = df.columns.get_loc(c)
                    ws.set_column(col, col, 18, fmt_money)
            for c in pct_cols:
                if c in df.columns:
                    col = df.columns.get_loc(c)
                    ws.set_column(col, col, 14, fmt_pct)
            return ws

        _style_table(
            "Summary Data",
            df_summary,
            money_cols=("ext_total_amount", "int_total_amount", "matched_amount", "break_amount"),
            pct_cols=("match_rate",),
        )
        _style_table("Matched Transactions", df_matches, money_cols=("amount",), pct_cols=("match_score",))
        ws_disc = _style_table("Discrepancy Alert", df_breaks, money_cols=("amount",), pct_cols=())
        _style_table("Break Counts", df_break_counts, money_cols=("break_amount",), pct_cols=())

        # Conditional formatting for discrepancies
        if not df_breaks.empty and "amount" in df_breaks.columns:
            amt_col = df_breaks.columns.get_loc("amount")
            # Highlight large absolute discrepancies
            ws_disc.conditional_format(
                1,
                amt_col,
                max(1, df_breaks.shape[0]),
                amt_col,
                {
                    "type": "formula",
                    "criteria": f"=ABS(${chr(ord('A') + amt_col)}2)>={discrepancy_highlight_amount}",
                    "format": fmt_highlight,
                },
            )
        if not df_breaks.empty and "break_code" in df_breaks.columns:
            bc_col = df_breaks.columns.get_loc("break_code")
            last_row = max(1, df_breaks.shape[0])
            ws_disc.conditional_format(
                1,
                bc_col,
                last_row,
                bc_col,
                {"type": "text", "criteria": "containing", "value": "EXT_ONLY", "format": fmt_warn},
            )
            ws_disc.conditional_format(
                1,
                bc_col,
                last_row,
                bc_col,
                {"type": "text", "criteria": "containing", "value": "INT_ONLY", "format": fmt_warn},
            )

        # Dashboard tab (stakeholder-friendly)
        ws_dash = wb.add_worksheet("Summary Dashboard")
        writer.sheets["Summary Dashboard"] = ws_dash
        ws_dash.set_column(0, 0, 4)
        ws_dash.set_column(1, 1, 26)
        ws_dash.set_column(2, 2, 22)
        ws_dash.set_column(3, 6, 18)

        ws_dash.write(0, 1, "Reconciliation Summary Dashboard", fmt_title)
        ws_dash.write(2, 1, "Run ID", fmt_label)
        ws_dash.write(2, 2, run_summary.get("run_id"))
        ws_dash.write(3, 1, "Run Date", fmt_label)
        ws_dash.write(3, 2, str(run_summary.get("run_date")))
        ws_dash.write(4, 1, "Source", fmt_label)
        ws_dash.write(4, 2, run_summary.get("source_system"))

        # KPIs
        ws_dash.write(2, 4, "Match Rate", fmt_label)
        ws_dash.write_number(2, 5, float(run_summary.get("match_rate", 0.0)), fmt_pct)
        ws_dash.write(3, 4, "Matched Count", fmt_label)
        ws_dash.write_number(3, 5, float(run_summary.get("matched_count", 0)), fmt_kpi)
        ws_dash.write(4, 4, "Break Count", fmt_label)
        ws_dash.write_number(4, 5, float(run_summary.get("break_count", 0)), fmt_kpi)

        ws_dash.write(6, 1, "Totals", fmt_title)
        ws_dash.write(7, 1, "External (count / amount)", fmt_label)
        ws_dash.write_number(7, 2, float(run_summary.get("ext_total_count", 0)))
        ws_dash.write_number(7, 3, float(run_summary.get("ext_total_amount", 0.0)), fmt_money)
        ws_dash.write(8, 1, "Internal (count / amount)", fmt_label)
        ws_dash.write_number(8, 2, float(run_summary.get("int_total_count", 0)))
        ws_dash.write_number(8, 3, float(run_summary.get("int_total_amount", 0.0)), fmt_money)
        ws_dash.write(9, 1, "Matched (count / amount)", fmt_label)
        ws_dash.write_number(9, 2, float(run_summary.get("matched_count", 0)))
        ws_dash.write_number(9, 3, float(run_summary.get("matched_amount", 0.0)), fmt_money)
        ws_dash.write(10, 1, "Breaks (count / amount)", fmt_label)
        ws_dash.write_number(10, 2, float(run_summary.get("break_count", 0)))
        ws_dash.write_number(10, 3, float(run_summary.get("break_amount", 0.0)), fmt_money)

        # Break breakdown block
        ws_dash.write(12, 1, "Break Breakdown", fmt_title)
        ws_dash.write(13, 1, "break_code", fmt_header)
        ws_dash.write(13, 2, "break_count", fmt_header)
        ws_dash.write(13, 3, "break_amount", fmt_header)

        for i, row in enumerate(break_counts_rows, start=14):
            ws_dash.write(i, 1, row.get("break_code"))
            ws_dash.write_number(i, 2, float(row.get("break_count", 0)))
            ws_dash.write_number(i, 3, float(row.get("break_amount", 0.0)), fmt_money)

        ws_dash.freeze_panes(1, 0)

    return out
