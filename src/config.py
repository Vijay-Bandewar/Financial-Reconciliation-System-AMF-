from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel
import os


class Settings(BaseModel):
    oracle_user: str
    oracle_password: str
    oracle_dsn: str
    internal_txn_source: str
    output_dir: Path = Path("data/output")
    discrepancy_highlight_amount: float = 100000.0


def _env_str(key: str, default: str | None = None) -> str:
    raw = os.getenv(key, default)
    if raw is None:
        raise KeyError(key)
    v = str(raw).strip()
    if len(v) >= 2 and ((v[0] == v[-1] == '"') or (v[0] == v[-1] == "'")):
        v = v[1:-1].strip()
    return v


def load_settings(env_path: str | os.PathLike[str] | None = None) -> Settings:
    # Load repo-root `.env` by default (caller can override).
    load_dotenv(dotenv_path=env_path, override=False)

    output_dir = _env_str("OUTPUT_DIR", "data/output")
    discrepancy_highlight_amount = float(_env_str("DISCREPANCY_HIGHLIGHT_AMOUNT", "100000"))
    return Settings(
        oracle_user=_env_str("ORACLE_USER"),
        oracle_password=_env_str("ORACLE_PASSWORD"),
        oracle_dsn=_env_str("ORACLE_DSN"),
        internal_txn_source=_env_str("INTERNAL_TXN_SOURCE", "INTERNAL_TXN_VW"),
        output_dir=Path(output_dir),
        discrepancy_highlight_amount=discrepancy_highlight_amount,
    )
