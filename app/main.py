from fastapi import FastAPI
import pandas as pd
from threading import Thread
from starlette.middleware.cors import CORSMiddleware
from .api.router import router as api_router
from .core.settings import get_settings
from .db.session import init_db
from .services.db_dataframe import load_main_dataframe_from_db
from .services.pipeline import refresh_market_data

app = FastAPI(
    title="IT Market Analysis API",
    description="API для аналізу та прогнозування трендів на IT-ринку України."
)

def _refresh_on_startup_background():
    try:
        refresh_market_data(app)
    except Exception as exc:
        app.state.main_df = pd.DataFrame()
        app.state.data_status = {"status": "failed", "error": str(exc)}

settings = get_settings()
origins = [item.strip() for item in settings.cors_origins.split(",") if item and item.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=settings.cors_allow_origin_regex or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    """Ініціалізує БД та завантажує дані в пам'ять для аналітики."""
    init_db()
    try:
        app.state.main_df = load_main_dataframe_from_db()
    except Exception:
        app.state.main_df = pd.DataFrame()
    app.state.data_status = {
        "status": "ready_from_db",
        "rows_in_memory": int(len(app.state.main_df)),
    }
    if settings.refresh_on_startup:
        app.state.data_status["status"] = "refreshing_in_background"
        Thread(target=_refresh_on_startup_background, daemon=True).start()

app.include_router(api_router, prefix="/api")

@app.get("/")
def read_root():
    return {"message": "Welcome! Go to /docs for API documentation."}