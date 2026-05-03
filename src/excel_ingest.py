from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
from pathlib import Path
from typing import Iterable

import pandas as pd


REQUIRED_COLUMNS = {
    "txn_date",
    "amount",
    "currency",
    "reference",
    "account",
}


@dataclass(frozen=True)
class ExternalTxnRow:
    source_row_num: int
    txn_date: date
    amount: float
    currency: str
    reference: str
    account: str
    narration: str | None
    counterparty: str | None
    row_hash: str


def _norm_str(x: object) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return ""
    return str(x).strip()


def _row_hash(parts: Iterable[str]) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\x1f")
    return h.hexdigest()


def read_external_excel(path: str | Path, *, sheet_name: str | int | None = 0) -> list[ExternalTxnRow]:
    p = Path(path)
    df = pd.read_excel(p, sheet_name=sheet_name, engine="openpyxl")
    df.columns = [str(c).strip() for c in df.columns]

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"External Excel missing required columns: {sorted(missing)}. Found: {list(df.columns)}")

    # Minimal normalization; tailor this once your exact format is confirmed.
    df = df.copy()
    df["txn_date"] = pd.to_datetime(df["txn_date"]).dt.date
    df["amount"] = pd.to_numeric(df["amount"])
    df["currency"] = df["currency"].map(_norm_str).str.upper()
    df["reference"] = df["reference"].map(_norm_str)
    df["account"] = df["account"].map(_norm_str)
    df["narration"] = df.get("narration", pd.Series([None] * len(df))).map(_norm_str)
    df["counterparty"] = df.get("counterparty", pd.Series([None] * len(df))).map(_norm_str)

    rows: list[ExternalTxnRow] = []
    for idx, r in df.iterrows():
        source_row_num = int(idx) + 2  # 1-based row + header
        txn_date = r["txn_date"]
        amount = float(r["amount"])
        currency = str(r["currency"])
        reference = str(r["reference"])
        account = str(r["account"])
        narration = str(r["narration"]) if r["narration"] != "" else None
        counterparty = str(r["counterparty"]) if r["counterparty"] != "" else None
        row_hash = _row_hash(
            [
                str(txn_date),
                f"{amount:.2f}",
                currency,
                reference.upper(),
                account.upper(),
            ]
        )
        rows.append(
            ExternalTxnRow(
                source_row_num=source_row_num,
                txn_date=txn_date,
                amount=amount,
                currency=currency,
                reference=reference,
                account=account,
                narration=narration,
                counterparty=counterparty,
                row_hash=row_hash,
            )
        )
    return rows
