from fastapi import APIRouter, Request, HTTPException, Query
from typing import List, Optional
from ...services.forecaster import MarketForecaster

router = APIRouter()


@router.get("/")
def get_skills_analysis(
        request: Request,
        category: Optional[str] = None,
        experience_min: Optional[int] = 0,
        skills: Optional[List[str]] = Query(None),
):
    """Аналіз важливості навичок та їх розподіл по зарплатним квартилям."""
    main_df = request.app.state.main_df
    required_columns = {"category_name", "experience", "avg_salary", "skills", "salary_quartile"}
    if main_df is None or main_df.empty or not required_columns.issubset(set(main_df.columns)):
        raise HTTPException(
            status_code=503,
            detail="Дані ще не готові для аналітики. Запусти оновлення через /api/system/refresh.",
        )
    segment_df = main_df.copy()
    if category:
        segment_df = segment_df[segment_df["category_name"] == category]
    if experience_min is not None:
        segment_df = segment_df[segment_df["experience"] >= (experience_min or 0)]
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
                "average_experience": 0.0,
            },
            "skill_importance": {
                "skill_importance_for_salary": []
            },
            "top_skills_by_quartile": {
                "Q1 (Lowest)": [],
                "Q2": [],
                "Q3": [],
                "Q4 (Top)": [],
            }
        }

    salary_df = segment_df[segment_df["avg_salary"].notna()].copy()
    forecaster = MarketForecaster(salary_df)
    skill_importance = forecaster.analyze_skills()

    exploded_skills = salary_df[salary_df["salary_quartile"].notna()].explode('skills')
    top_skills_by_quartile = {}
    for q in ['Q1 (Lowest)', 'Q2', 'Q3', 'Q4 (Top)']:
        top_skills = exploded_skills[exploded_skills['salary_quartile'] == q]['skills'].value_counts().nlargest(5)
        top_skills_by_quartile[q] = top_skills.reset_index().to_dict(orient='records')

    summary = {
        "total_vacancies": int(len(segment_df)),
        "median_salary": float(salary_df["avg_salary"].median()) if not salary_df.empty else 0.0,
        "average_experience": float(segment_df["experience"].mean()),
    }

    return {
        "summary": summary,
        "skill_importance": skill_importance,
        "top_skills_by_quartile": top_skills_by_quartile
    }