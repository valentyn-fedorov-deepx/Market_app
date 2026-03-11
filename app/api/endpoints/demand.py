from fastapi import APIRouter, HTTPException, Query, Request
from typing import List, Optional
import pandas as pd
from ...services.forecaster_advanced import MarketForecasterAdvanced

router = APIRouter()


@router.get("/")
def get_demand_analysis(
        request: Request,
        category: Optional[str] = None,
        experience_min: Optional[int] = None,
        skills: Optional[List[str]] = Query(None),
        forecast_days: int = 365
):
    """Аналіз попиту з фільтрами та прогнозом попиту."""
    main_df = request.app.state.main_df
    required_columns = {"category_name", "experience", "skills", "published", "avg_salary"}
    if main_df is None or main_df.empty or not required_columns.issubset(set(main_df.columns)):
        raise HTTPException(
            status_code=503,
            detail="Дані ще не готові для аналітики. Запусти оновлення через /api/system/refresh.",
        )
    filtered_df = main_df.copy()

    if category:
        filtered_df = filtered_df[filtered_df["category_name"] == category]
    if experience_min is not None:
        filtered_df = filtered_df[filtered_df["experience"] >= experience_min]

    if skills:
        required_skills = {skill.strip().lower() for skill in skills if skill and skill.strip()}
        if required_skills:
            filtered_df = filtered_df[
                filtered_df["skills"].apply(
                    lambda x: required_skills.issubset({str(skill).strip().lower() for skill in (x or [])})
                )
            ]

    if filtered_df.empty:
        return {
            "summary": {
                "total_vacancies": 0,
                "median_salary": 0.0,
                "average_salary": 0.0,
                "average_experience": 0.0,
            },
            "historical_demand": {
                "dates": [],
                "values": [],
            },
            "experience_distribution": [],
            "demand_forecast": None,
        }

    demand_ts = filtered_df.groupby(pd.Grouper(key="published", freq="ME")).size()
    demand_forecast = None
    if category:
        advanced_forecaster = MarketForecasterAdvanced(filtered_df)
        demand_forecast = advanced_forecaster.get_prophet_forecast(
            category_name=category,
            periods=forecast_days
        )

    experience_distribution = (
        filtered_df["experience"]
        .value_counts()
        .rename_axis("experience")
        .reset_index(name="count")
        .sort_values("experience")
    )
    salary_df = filtered_df[filtered_df["avg_salary"].notna()]

    summary = {
        "total_vacancies": int(len(filtered_df)),
        "median_salary": float(salary_df["avg_salary"].median()) if not salary_df.empty else 0.0,
        "average_salary": float(salary_df["avg_salary"].mean()) if not salary_df.empty else 0.0,
        "average_experience": float(filtered_df["experience"].mean()),
    }

    return {
        "summary": summary,
        "historical_demand": {
            "dates": demand_ts.index.strftime("%Y-%m").tolist(),
            "values": demand_ts.values.tolist(),
        },
        "experience_distribution": experience_distribution.to_dict(orient="records"),
        "demand_forecast": demand_forecast,
    }
