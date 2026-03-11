from fastapi import APIRouter, Request, HTTPException, Query
from typing import Optional, List
from ...services.forecaster_advanced import MarketForecasterAdvanced

router = APIRouter()


@router.get("/")
def get_salary_analysis(
        request: Request,
        category: str,
        experience_min: Optional[int] = 0,
        forecast_days: int = 365,
        skills: Optional[List[str]] = Query(None),
):
    """Прогноз попиту та детальний аналіз зарплат для категорії."""
    main_df = request.app.state.main_df
    required_columns = {"category_name", "experience", "avg_salary", "salary_quartile"}
    if main_df is None or main_df.empty or not required_columns.issubset(set(main_df.columns)):
        raise HTTPException(
            status_code=503,
            detail="Дані ще не готові для аналітики. Запусти оновлення через /api/system/refresh.",
        )
    segment_df = main_df[
        (main_df["category_name"] == category)
        & (main_df["experience"] >= (experience_min or 0))
    ]

    if skills:
        required_skills = {skill.strip().lower() for skill in skills if skill and skill.strip()}
        if required_skills:
            segment_df = segment_df[
                segment_df["skills"].apply(
                    lambda x: required_skills.issubset({str(skill).strip().lower() for skill in (x or [])})
                )
            ]

    if segment_df.empty:
        return {
            "summary": {
                "total_vacancies": 0,
                "median_salary": 0.0,
                "average_salary": 0.0,
                "top_quartile_median": None,
            },
            "demand_forecast": None,
            "salary_distribution": {
                "by_quartile": [],
                "by_experience": []
            }
        }

    advanced_forecaster = MarketForecasterAdvanced(segment_df)
    demand_forecast = advanced_forecaster.get_prophet_forecast(category, forecast_days)

    salary_df = segment_df[segment_df["avg_salary"].notna()].copy()
    salary_by_quartile = salary_df[salary_df["salary_quartile"].notna()].groupby('salary_quartile')['avg_salary'].agg(
        ['min', 'max', 'median', 'mean']).round(0).reset_index().to_dict(orient='records')
    salary_by_experience = salary_df.groupby('experience')['avg_salary'].median().round(0).reset_index().to_dict(
        orient='records')
    summary = {
        "total_vacancies": int(len(segment_df)),
        "median_salary": float(salary_df["avg_salary"].median()) if not salary_df.empty else 0.0,
        "average_salary": float(salary_df["avg_salary"].mean()) if not salary_df.empty else 0.0,
        "top_quartile_median": float(
            salary_df[salary_df["salary_quartile"] == "Q4 (Top)"]["avg_salary"].median()
        ) if not salary_df[salary_df["salary_quartile"] == "Q4 (Top)"].empty else None,
    }

    return {
        "summary": summary,
        "demand_forecast": demand_forecast,
        "salary_distribution": {
            "by_quartile": salary_by_quartile,
            "by_experience": salary_by_experience
        }
    }