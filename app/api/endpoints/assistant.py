from typing import Optional
from fastapi import APIRouter, HTTPException, Request
import pandas as pd
from pydantic import BaseModel, Field
from ...db.session import SessionLocal
from ...services.assistant import AssistantService


router = APIRouter()
assistant_service = AssistantService()


class AssistantChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: Optional[str] = None
    category: Optional[str] = None


class AssistantReportRequest(BaseModel):
    category: Optional[str] = None
    horizon_days: int = Field(default=90, ge=14, le=365)


@router.get("/insights")
def get_assistant_insights(request: Request, category: Optional[str] = None):
    main_df = getattr(request.app.state, "main_df", None)
    if main_df is None:
        main_df = pd.DataFrame()

    with SessionLocal() as session:
        return assistant_service.generate_insights(session=session, df=main_df, category=category)


@router.post("/report")
def create_assistant_report(payload: AssistantReportRequest, request: Request):
    main_df = getattr(request.app.state, "main_df", None)
    if main_df is None:
        main_df = pd.DataFrame()

    with SessionLocal() as session:
        return assistant_service.generate_report(
            session=session,
            df=main_df,
            category=payload.category,
            horizon_days=payload.horizon_days,
        )


@router.post("/chat")
def chat_with_assistant(payload: AssistantChatRequest, request: Request):
    main_df = getattr(request.app.state, "main_df", None)
    if main_df is None:
        main_df = pd.DataFrame()

    with SessionLocal() as session:
        return assistant_service.chat(
            session=session,
            df=main_df,
            user_message=payload.message,
            session_id=payload.session_id,
            category=payload.category,
        )
