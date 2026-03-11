from fastapi import APIRouter, Request
from pydantic import BaseModel
from ...services.pipeline import refresh_market_data


router = APIRouter()


class RefreshRequest(BaseModel):
    force_csv: bool = False


@router.get("/data-status")
def get_data_status(request: Request):
    status = getattr(request.app.state, "data_status", None) or {}
    rows = int(len(getattr(request.app.state, "main_df", [])))
    return {
        "status": "ok",
        "rows": rows,
        "data_status": status,
    }


@router.post("/refresh")
def refresh_data(request: Request, payload: RefreshRequest):
    status = refresh_market_data(request.app, force_csv=payload.force_csv)
    return {
        "status": "ok",
        "data_status": status,
    }
