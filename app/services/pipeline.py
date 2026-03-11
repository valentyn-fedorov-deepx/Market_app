from datetime import datetime
from fastapi import FastAPI
from ..db.session import SessionLocal
from .db_dataframe import load_main_dataframe_from_db
from .ingestion import run_ingestion_pipeline


def refresh_market_data(app: FastAPI, force_csv: bool = False) -> dict:
    with SessionLocal() as session:
        ingestion_summary = run_ingestion_pipeline(session, force_csv=force_csv)

    df = load_main_dataframe_from_db()
    app.state.main_df = df

    status = {
        "last_refresh": datetime.utcnow().isoformat(),
        "rows_in_memory": int(len(df)),
        "total_upserted": int(ingestion_summary.get("total_upserted", 0)),
        "used_csv_fallback": bool(ingestion_summary.get("used_csv_fallback", False)),
        "errors": ingestion_summary.get("errors", []),
        "runs": ingestion_summary.get("runs", []),
    }
    app.state.data_status = status
    return status
