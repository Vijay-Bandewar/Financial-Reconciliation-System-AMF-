# Financial-Reconciliation-System-AMF-
This project automates the pipeline using Python (Pandas) for Excel ingestion, Oracle for storage, and PL/SQL for matching logic. By logging discrepancies and generating automated stakeholder dashboards with high-value alerts, it accelerates reporting and ensures data integrity.


End-to-end pipeline:

- **Excel (external)** → Python (Pandas) → **DB staging tables**
- **PL/SQL stored procedures** reconcile external vs internal records
- **Excel output** dashboards + break lists for business users

### Folder layout

- `src/`: Python pipeline (ingest → reconcile → report)
- `sql/`: Oracle DDL + PL/SQL packages (schema, procedures)
- `config/`: configuration templates
- `data/input/`: drop daily external Excel files here
- `data/output/`: generated outputs (Excel dashboards, break extracts)

### Prerequisites

- Python 3.10+
- Oracle client connectivity (e.g. Instant Client) and access to an Oracle DB schema

### Quick start

1) Create a venv and install dependencies:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

2) Copy env template and fill it:

- Copy `config/.env.example` to `.env` in the repo root
- Set Oracle connection details and internal table/view name

3) Create DB objects (run in your schema):

- Run `sql/schema.sql`
- Run `sql/recon_pkg.sql`

4) Drop an Excel file into `data/input/` and run:

```bash
python -m src.main --source AMF --run-date 2026-04-29 --input "data/input/daily.xlsx"
```

Outputs are written into `data/output/`.

### Notes

- This scaffold assumes **Oracle** (PL/SQL). If you’re on SQL Server/Postgres, we can swap the SQL layer accordingly.
- The ingestion step is strict about required columns; adjust `src/excel_ingest.py` once you confirm the exact external Excel layout.
