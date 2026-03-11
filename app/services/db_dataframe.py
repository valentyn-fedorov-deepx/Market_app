import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from ..db.models import Vacancy
from ..db.session import SessionLocal
from .data_loader import prepare_dataframe


def load_main_dataframe_from_db() -> pd.DataFrame:
    with SessionLocal() as session:
        vacancies = session.execute(
            select(Vacancy).options(
                selectinload(Vacancy.category),
                selectinload(Vacancy.company),
                selectinload(Vacancy.skills),
            )
        ).scalars().all()

    records = []
    for vacancy in vacancies:
        records.append(
            {
                "id": vacancy.source_job_id,
                "title": vacancy.title,
                "company_name": vacancy.company.name if vacancy.company else "Unknown",
                "long_description": vacancy.long_description,
                "category_name": vacancy.category.name if vacancy.category else "Unknown",
                "experience": vacancy.experience,
                "published": vacancy.published,
                "public_salary_min": vacancy.public_salary_min,
                "public_salary_max": vacancy.public_salary_max,
                "avg_salary": vacancy.avg_salary,
                "skills": [skill.name for skill in vacancy.skills],
                "domain": vacancy.domain,
                "source": vacancy.source,
            }
        )

    if not records:
        return pd.DataFrame()

    return prepare_dataframe(pd.DataFrame(records))
