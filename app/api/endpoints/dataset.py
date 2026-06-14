import uuid
from datetime import datetime
from threading import Thread
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import selectinload

from ...db.models import Category, Company, Vacancy
from ...db.session import SessionLocal
from ...services.db_dataframe import load_main_dataframe_from_db
from ...services.ingestion import (
    _get_or_create_category,
    _get_or_create_company,
    _get_or_create_skill,
    _safe_float,
    _slugify,
)

router = APIRouter()

MANUAL_SOURCE = "manual"
MAX_PAGE_SIZE = 200

SORT_COLUMNS = {
    "id": Vacancy.id,
    "title": Vacancy.title,
    "experience": Vacancy.experience,
    "published": Vacancy.published,
    "avg_salary": Vacancy.avg_salary,
    "public_salary_min": Vacancy.public_salary_min,
    "public_salary_max": Vacancy.public_salary_max,
    "source": Vacancy.source,
    "company_name": Company.name,
    "category_name": Category.name,
}


class VacancyCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    company_name: str = Field(default="Unknown", max_length=255)
    category_name: str = Field(default="Other", max_length=255)
    experience: int = Field(default=0, ge=0, le=50)
    published: Optional[datetime] = None
    public_salary_min: Optional[float] = Field(default=None, ge=0)
    public_salary_max: Optional[float] = Field(default=None, ge=0)
    skills: list[str] = Field(default_factory=list)
    domain: Optional[str] = None
    long_description: Optional[str] = None


class VacancyUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=500)
    company_name: Optional[str] = Field(default=None, max_length=255)
    category_name: Optional[str] = Field(default=None, max_length=255)
    experience: Optional[int] = Field(default=None, ge=0, le=50)
    published: Optional[datetime] = None
    public_salary_min: Optional[float] = Field(default=None, ge=0)
    public_salary_max: Optional[float] = Field(default=None, ge=0)
    skills: Optional[list[str]] = None
    domain: Optional[str] = None
    long_description: Optional[str] = None


def _serialize(vacancy: Vacancy) -> dict:
    return {
        "id": vacancy.id,
        "source": vacancy.source,
        "source_job_id": vacancy.source_job_id,
        "title": vacancy.title,
        "company_name": vacancy.company.name if vacancy.company else None,
        "category_name": vacancy.category.name if vacancy.category else None,
        "experience": vacancy.experience,
        "published": vacancy.published.isoformat() if vacancy.published else None,
        "public_salary_min": vacancy.public_salary_min,
        "public_salary_max": vacancy.public_salary_max,
        "avg_salary": vacancy.avg_salary,
        "domain": vacancy.domain,
        "skills": sorted(skill.name for skill in vacancy.skills),
    }


def _avg_salary(salary_min: float | None, salary_max: float | None) -> float | None:
    if salary_min is not None and salary_max is not None:
        return (salary_min + salary_max) / 2
    return salary_min if salary_min is not None else salary_max


def _refresh_cache_async(request: Request) -> None:
    """Rebuild the in-memory analytics DataFrame in the background after a write."""

    def _worker():
        try:
            request.app.state.main_df = load_main_dataframe_from_db()
        except Exception:
            pass

    Thread(target=_worker, daemon=True).start()


def _load_with_relations(session, vacancy_id: int) -> Vacancy | None:
    return session.execute(
        select(Vacancy)
        .options(
            selectinload(Vacancy.category),
            selectinload(Vacancy.company),
            selectinload(Vacancy.skills),
        )
        .where(Vacancy.id == vacancy_id)
    ).scalar_one_or_none()


def _apply_skills(session, vacancy: Vacancy, skills: list[str]) -> None:
    skill_cache: dict = {}
    entities = []
    for raw in skills:
        name = str(raw).strip()
        if name:
            entities.append(_get_or_create_skill(session, skill_cache, name))
    vacancy.skills = entities


@router.get("/sources")
def get_dataset_sources(request: Request):
    with SessionLocal() as session:
        rows = session.execute(select(Vacancy.source).distinct().order_by(Vacancy.source)).scalars().all()
    return {"sources": [row for row in rows if row]}


@router.get("/")
def list_dataset(
    request: Request,
    q: Optional[str] = None,
    category: Optional[str] = None,
    source: Optional[str] = None,
    experience_min: Optional[int] = None,
    experience_max: Optional[int] = None,
    sort_by: str = "published",
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=MAX_PAGE_SIZE),
):
    """Paginated, searchable, sortable view over all ingested vacancies."""
    conditions = []
    if q and q.strip():
        like = f"%{q.strip()}%"
        conditions.append(or_(Vacancy.title.ilike(like), Company.name.ilike(like), Category.name.ilike(like)))
    if category and category.strip():
        conditions.append(Category.name == category.strip())
    if source and source.strip():
        conditions.append(Vacancy.source == source.strip())
    if experience_min is not None:
        conditions.append(Vacancy.experience >= experience_min)
    if experience_max is not None:
        conditions.append(Vacancy.experience <= experience_max)

    sort_column = SORT_COLUMNS.get(sort_by, Vacancy.published)
    sort_column = sort_column.asc() if sort_dir == "asc" else sort_column.desc()

    with SessionLocal() as session:
        count_stmt = (
            select(func.count(Vacancy.id))
            .select_from(Vacancy)
            .join(Category, Vacancy.category_id == Category.id)
            .join(Company, Vacancy.company_id == Company.id)
        )
        data_stmt = (
            select(Vacancy)
            .join(Category, Vacancy.category_id == Category.id)
            .join(Company, Vacancy.company_id == Company.id)
            .options(
                selectinload(Vacancy.category),
                selectinload(Vacancy.company),
                selectinload(Vacancy.skills),
            )
        )
        if conditions:
            criteria = and_(*conditions)
            count_stmt = count_stmt.where(criteria)
            data_stmt = data_stmt.where(criteria)

        total = session.execute(count_stmt).scalar_one()
        rows = (
            session.execute(
                data_stmt.order_by(sort_column).offset((page - 1) * page_size).limit(page_size)
            )
            .scalars()
            .all()
        )
        items = [_serialize(row) for row in rows]

    return {
        "items": items,
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


@router.post("/")
def create_vacancy(payload: VacancyCreate, request: Request):
    salary_min = _safe_float(payload.public_salary_min)
    salary_max = _safe_float(payload.public_salary_max)
    with SessionLocal() as session:
        category = _get_or_create_category(
            session, {}, slug=_slugify(payload.category_name), name=payload.category_name.strip() or "Other"
        )
        company = _get_or_create_company(session, {}, payload.company_name)
        vacancy = Vacancy(
            source=MANUAL_SOURCE,
            source_job_id=uuid.uuid4().hex,
            title=payload.title.strip(),
            long_description=payload.long_description,
            domain=payload.domain,
            experience=int(payload.experience or 0),
            published=payload.published or datetime.utcnow(),
            public_salary_min=salary_min,
            public_salary_max=salary_max,
            avg_salary=_avg_salary(salary_min, salary_max),
            category=category,
            company=company,
            is_active=True,
        )
        session.add(vacancy)
        _apply_skills(session, vacancy, payload.skills)
        session.commit()
        vacancy = _load_with_relations(session, vacancy.id)
        result = _serialize(vacancy)

    _refresh_cache_async(request)
    return result


@router.put("/{vacancy_id}")
def update_vacancy(vacancy_id: int, payload: VacancyUpdate, request: Request):
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields provided to update.")

    with SessionLocal() as session:
        vacancy = _load_with_relations(session, vacancy_id)
        if vacancy is None:
            raise HTTPException(status_code=404, detail="Vacancy not found.")

        if "category_name" in data:
            name = (data["category_name"] or "Other").strip() or "Other"
            vacancy.category = _get_or_create_category(session, {}, slug=_slugify(name), name=name)
        if "company_name" in data:
            vacancy.company = _get_or_create_company(session, {}, data["company_name"])
        if "title" in data and data["title"]:
            vacancy.title = data["title"].strip()
        if "experience" in data and data["experience"] is not None:
            vacancy.experience = int(data["experience"])
        if "published" in data and data["published"] is not None:
            vacancy.published = data["published"]
        if "domain" in data:
            vacancy.domain = data["domain"]
        if "long_description" in data:
            vacancy.long_description = data["long_description"]
        if "public_salary_min" in data:
            vacancy.public_salary_min = _safe_float(data["public_salary_min"])
        if "public_salary_max" in data:
            vacancy.public_salary_max = _safe_float(data["public_salary_max"])
        if "skills" in data and data["skills"] is not None:
            _apply_skills(session, vacancy, data["skills"])

        vacancy.avg_salary = _avg_salary(vacancy.public_salary_min, vacancy.public_salary_max)
        session.commit()
        vacancy = _load_with_relations(session, vacancy_id)
        result = _serialize(vacancy)

    _refresh_cache_async(request)
    return result


@router.delete("/{vacancy_id}")
def delete_vacancy(vacancy_id: int, request: Request):
    with SessionLocal() as session:
        vacancy = session.get(Vacancy, vacancy_id)
        if vacancy is None:
            raise HTTPException(status_code=404, detail="Vacancy not found.")
        session.delete(vacancy)
        session.commit()

    _refresh_cache_async(request)
    return {"status": "deleted", "id": vacancy_id}
