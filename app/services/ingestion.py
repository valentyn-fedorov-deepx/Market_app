import ast
import re
from datetime import datetime, timedelta
import httpx
import pandas as pd
try:
    import polars as pl
except Exception:  # pragma: no cover
    pl = None
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from ..core.settings import get_settings
from ..db.models import Category, Company, IngestionRun, Skill, Vacancy


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower())
    return cleaned.strip("-") or "unknown"


def _safe_int(value, default: int = 0) -> int:
    try:
        if pd.isna(value):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _safe_float(value) -> float | None:
    try:
        if value is None or pd.isna(value) or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_datetime(value) -> datetime | None:
    dt = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(dt):
        return None
    return dt.tz_convert(None).to_pydatetime()


def _extract_salary_range_from_text(salary_text: str | None) -> tuple[float | None, float | None]:
    if not salary_text:
        return None, None
    numbers = re.findall(r"\d+(?:[.,]\d+)?", salary_text.replace(",", ""))
    if not numbers:
        return None, None
    values = [float(number) for number in numbers]
    if len(values) == 1:
        return values[0], values[0]
    return min(values), max(values)


def _parse_category_name(category_value) -> tuple[str, str]:
    if isinstance(category_value, dict):
        category_id = str(category_value.get("id") or category_value.get("name") or "unknown")
        category_name = str(category_value.get("name") or category_value.get("id") or "Unknown")
        return category_id, category_name

    if isinstance(category_value, str):
        stripped = category_value.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                parsed = ast.literal_eval(stripped)
                return _parse_category_name(parsed)
            except (ValueError, SyntaxError):
                pass
        return _slugify(stripped), stripped or "Unknown"

    return "unknown", "Unknown"


def _parse_skills(raw_skills) -> list[str]:
    if isinstance(raw_skills, list):
        return sorted(set(str(skill).strip() for skill in raw_skills if str(skill).strip()))
    if isinstance(raw_skills, str):
        return sorted(set(chunk.strip() for chunk in raw_skills.split(",") if chunk.strip()))
    return []


CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "Software Development": [
        "engineer", "developer", "software", "backend", "frontend", "fullstack", "full stack",
        "mobile", "ios", "android", "web", "python", "java", "javascript", "typescript", "react",
        "node", "golang", "ruby", "php", "dotnet", "c#", "c++",
    ],
    "DevOps / Sysadmin": [
        "devops", "sre", "sysadmin", "infrastructure", "cloud", "site reliability",
        "platform engineer", "kubernetes", "terraform", "linux",
    ],
    "Data": ["data", "analytics", "ml", "machine learning", "ai", "bi", "data scientist", "etl"],
    "Design": ["design", "designer", "ux", "ui", "product designer"],
    "Marketing": ["marketing", "seo", "growth", "ads", "ppc", "performance marketing", "content marketing"],
    "Writing": ["writer", "copywriter", "content", "editor", "documentation", "technical writer"],
    "Sales": ["sales", "account executive", "business development", "bdr", "sdr"],
    "Product": ["product manager", "product owner", "pm"],
    "Support": ["support", "customer success", "helpdesk", "customer care"],
    "Security": ["security", "infosec", "soc", "penetration", "vulnerability"],
    "Finance": ["finance", "accountant", "accounting", "payroll", "controller"],
    "HR": ["hr", "recruit", "talent", "people operations"],
    "Operations": ["operations", "ops", "admin", "administrator", "office manager"],
}

CATEGORY_ALIASES: dict[str, str] = {
    "all others": "Other",
    "software development": "Software Development",
    "data": "Data",
    "design": "Design",
    "marketing": "Marketing",
    "product": "Product",
    "sales": "Sales",
    "sales / business": "Sales",
    "customer service": "Support",
    "support": "Support",
    "operations": "Operations",
    "project management": "Product",
    "security": "Security",
    "finance / legal": "Finance",
    "finance": "Finance",
    "devops / sysadmin": "DevOps / Sysadmin",
    "devops and sysadmin": "DevOps / Sysadmin",
    "qa": "Software Development",
    "ai / ml": "Data",
    "writing": "Writing",
}


EXPERIENCE_KEYWORDS: list[tuple[list[str], int]] = [
    (["intern", "internship", "trainee", "entry level", "entry-level", "graduate"], 0),
    (["junior", "jr ", "jr.", "associate"], 1),
    (["middle", "mid-level", "mid level", "regular"], 3),
    (["senior", "sr ", "sr."], 5),
    (["staff", "lead", "principal", "architect", "head of", "director"], 7),
]


def _infer_category(title: str | None, tags: list[str] | None, raw_category: str | None = None) -> str:
    raw_text = (raw_category or "").strip().lower()
    if raw_text in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[raw_text]

    title_text = (title or "").lower()
    tags_text = " ".join(tags or []).lower()
    haystack = f"{raw_text} {title_text} {tags_text}".strip()
    haystack = f"{title_text} {tags_text}".strip()
    if not haystack:
        return "Other"
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            return category
    return "Other"


def _infer_experience_years(title: str | None, description: str | None, tags: list[str] | None) -> int:
    text = " ".join(
        [
            str(title or "").lower(),
            str(description or "").lower(),
            " ".join(tags or []).lower(),
        ]
    )
    if not text.strip():
        return 0

    years_matches = re.findall(r"(\d{1,2})\s*\+?\s*(?:years?|yrs?)", text)
    if years_matches:
        years = min(int(match) for match in years_matches)
        return max(0, min(years, 15))

    for keywords, years in EXPERIENCE_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return years
    return 0


TECH_SKILL_PATTERNS: list[tuple[str, str]] = [
    (r"\bpython\b", "Python"),
    (r"\bjava\b", "Java"),
    (r"\bjavascript\b|\bjs\b", "JavaScript"),
    (r"\btypescript\b|\bts\b", "TypeScript"),
    (r"\breact\b", "React"),
    (r"\bnode(?:\.js|js)?\b", "Node.js"),
    (r"\bvue(?:\.js|js)?\b", "Vue.js"),
    (r"\bangular\b", "Angular"),
    (r"\bgo\b|\bgolang\b", "Go"),
    (r"\bc#\b|\.net|\bdotnet\b", "C#/.NET"),
    (r"\bc\+\+\b", "C++"),
    (r"\bphp\b", "PHP"),
    (r"\bruby\b", "Ruby"),
    (r"\bsql\b", "SQL"),
    (r"\bpostgres(?:ql)?\b", "PostgreSQL"),
    (r"\bmysql\b", "MySQL"),
    (r"\bmongodb\b", "MongoDB"),
    (r"\bredis\b", "Redis"),
    (r"\baws\b", "AWS"),
    (r"\bgcp\b|google cloud", "GCP"),
    (r"\bazure\b", "Azure"),
    (r"\bdocker\b", "Docker"),
    (r"\bkubernetes\b|\bk8s\b", "Kubernetes"),
    (r"\bterraform\b", "Terraform"),
    (r"\bci/cd\b|\bci cd\b", "CI/CD"),
    (r"\bgraphql\b", "GraphQL"),
    (r"\brest\b", "REST"),
    (r"\bmachine learning\b|\bml\b", "AI/ML"),
    (r"\bdata engineering\b|\betl\b", "Data Engineering"),
    (r"\btableau\b", "Tableau"),
    (r"\bpower bi\b", "Power BI"),
]


def _extract_skills_from_text(*parts) -> list[str]:
    text = " ".join(str(part or "") for part in parts).lower()
    if not text.strip():
        return []
    found = []
    for pattern, skill in TECH_SKILL_PATTERNS:
        if re.search(pattern, text):
            found.append(skill)
    return sorted(set(found))


def _safe_datetime_from_epoch(value) -> datetime | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric <= 0:
        return None
    if numeric > 1_000_000_000_000:
        numeric = numeric / 1000.0
    try:
        return datetime.utcfromtimestamp(numeric)
    except (OverflowError, OSError, ValueError):
        return None


def _synthetic_published_from_id(value) -> datetime:
    try:
        seed = abs(int(value))
    except (TypeError, ValueError):
        seed = abs(hash(str(value)))
    days_back = seed % (365 * 5)
    return datetime.utcnow() - timedelta(days=days_back)


def _parse_first_location(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    matches = re.findall(r'"([^"]+)"', text)
    if matches:
        return matches[0]
    cleaned = text.strip("{} ")
    return cleaned or None


def _normalize_csv_records(csv_path: str) -> list[dict]:
    df = pd.read_csv(csv_path)
    records = []
    for row in df.to_dict(orient="records"):
        category_slug, category_name = _parse_category_name(row.get("category"))
        salary_min = _safe_float(row.get("public_salary_min"))
        salary_max = _safe_float(row.get("public_salary_max"))
        avg_salary = (
            ((salary_min or 0.0) + (salary_max or 0.0)) / 2 if salary_min is not None and salary_max is not None else None
        )
        records.append(
            {
                "source": "csv_fallback",
                "source_job_id": str(row.get("id")),
                "title": str(row.get("title") or "Unknown role"),
                "long_description": row.get("long_description"),
                "company_name": str(row.get("company_name") or "Unknown"),
                "category_slug": category_slug,
                "category_name": category_name,
                "experience": (
                    _safe_int(row.get("experience"), default=0)
                    or _infer_experience_years(
                        row.get("title"),
                        row.get("long_description"),
                        _parse_skills(row.get("skills")),
                    )
                ),
                "published": _safe_datetime(row.get("published")) or datetime.utcnow(),
                "public_salary_min": salary_min,
                "public_salary_max": salary_max,
                "avg_salary": avg_salary,
                "skills": _parse_skills(row.get("skills")),
                "domain": row.get("domain"),
            }
        )
    return records


def _fetch_remotive_records() -> list[dict]:
    settings = get_settings()
    with httpx.Client(timeout=30) as client:
        response = client.get(settings.remotive_api_url)
        response.raise_for_status()
        payload = response.json()

    jobs = payload.get("jobs", [])[: settings.remotive_limit]
    normalized = []
    for job in jobs:
        salary_min, salary_max = _extract_salary_range_from_text(job.get("salary"))
        tags = job.get("tags", []) or []
        raw_category = str(job.get("category") or "Other")
        category_name = _infer_category(job.get("title"), tags, raw_category=raw_category)
        category_slug = _slugify(category_name)
        normalized.append(
            {
                "source": "remotive",
                "source_job_id": str(job.get("id")),
                "title": str(job.get("title") or "Unknown role"),
                "long_description": job.get("description"),
                "company_name": str(job.get("company_name") or "Unknown"),
                "category_slug": category_slug,
                "category_name": category_name,
                "experience": _infer_experience_years(job.get("title"), job.get("description"), tags),
                "published": _safe_datetime(job.get("publication_date")) or datetime.utcnow(),
                "public_salary_min": salary_min,
                "public_salary_max": salary_max,
                "avg_salary": (
                    ((salary_min or 0.0) + (salary_max or 0.0)) / 2
                    if salary_min is not None and salary_max is not None
                    else None
                ),
                "skills": _parse_skills(tags),
                "domain": job.get("job_type") or job.get("candidate_required_location"),
            }
        )
    return normalized


def _fetch_arbeitnow_records() -> list[dict]:
    settings = get_settings()
    if not settings.arbeitnow_enabled:
        return []

    normalized: list[dict] = []
    page = 1
    max_pages = max(settings.arbeitnow_max_pages, 1)
    with httpx.Client(timeout=30) as client:
        while page <= max_pages:
            response = client.get(
                settings.arbeitnow_api_url,
                params={"page": page},
                headers={"User-Agent": "MarketAnalyzer/1.0 (+local-dev)"},
            )
            if response.status_code == 403:
                break
            response.raise_for_status()
            payload = response.json()
            jobs = payload.get("data", []) or []
            if not jobs:
                break
            for job in jobs:
                tags = job.get("tags", []) or []
                title = str(job.get("title") or "Unknown role")
                description = job.get("description")
                published_epoch = job.get("created_at")
                published = None
                if isinstance(published_epoch, (int, float)):
                    published = datetime.utcfromtimestamp(published_epoch)
                category_name = _infer_category(title, tags)
                normalized.append(
                    {
                        "source": "arbeitnow",
                        "source_job_id": str(job.get("slug") or ""),
                        "title": title,
                        "long_description": description,
                        "company_name": str(job.get("company_name") or "Unknown"),
                        "category_slug": _slugify(category_name),
                        "category_name": category_name,
                        "experience": _infer_experience_years(title, description, tags),
                        "published": published or datetime.utcnow(),
                        "public_salary_min": None,
                        "public_salary_max": None,
                        "avg_salary": None,
                        "skills": _parse_skills(tags),
                        "domain": "Remote" if job.get("remote") else job.get("location"),
                    }
                )
            page += 1

    return normalized


def _fetch_remoteok_records() -> list[dict]:
    settings = get_settings()
    if not settings.remoteok_enabled:
        return []

    with httpx.Client(timeout=30) as client:
        response = client.get(settings.remoteok_api_url)
        response.raise_for_status()
        payload = response.json()

    if not isinstance(payload, list):
        return []

    normalized: list[dict] = []
    for job in payload:
        if not isinstance(job, dict):
            continue
        job_id = job.get("id")
        title = job.get("position")
        company = job.get("company")
        if not job_id or not title or not company:
            continue
        tags = job.get("tags", []) or []
        description = job.get("description")
        salary_min = _safe_float(job.get("salary_min"))
        salary_max = _safe_float(job.get("salary_max"))
        if salary_min == 0:
            salary_min = None
        if salary_max == 0:
            salary_max = None
        published = _safe_datetime(job.get("date"))
        category_name = _infer_category(title, tags)
        normalized.append(
            {
                "source": "remoteok",
                "source_job_id": str(job_id),
                "title": str(title),
                "long_description": description,
                "company_name": str(company),
                "category_slug": _slugify(category_name),
                "category_name": category_name,
                "experience": _infer_experience_years(title, description, tags),
                "published": published or datetime.utcnow(),
                "public_salary_min": salary_min,
                "public_salary_max": salary_max,
                "avg_salary": None,
                "skills": _parse_skills(tags),
                "domain": job.get("location"),
            }
        )

    return normalized


HF_7M_PARQUET_URLS = [
    "https://huggingface.co/datasets/fantastic-jobs/7-million-jobs/resolve/refs%2Fconvert%2Fparquet/default/train/0000.parquet",
    "https://huggingface.co/datasets/fantastic-jobs/7-million-jobs/resolve/refs%2Fconvert%2Fparquet/default/train/0001.parquet",
]
HF_LINKEDIN_PARQUET_URL = (
    "https://huggingface.co/datasets/xanderios/linkedin-job-postings/resolve/refs%2Fconvert%2Fparquet/default/train/0000.parquet"
)


def _fetch_hf_7m_records() -> list[dict]:
    settings = get_settings()
    if not settings.hf_7m_enabled or settings.hf_7m_limit <= 0 or pl is None:
        return []

    normalized: list[dict] = []
    remaining = int(settings.hf_7m_limit)
    for url in HF_7M_PARQUET_URLS:
        if remaining <= 0:
            break
        frame = (
            pl.scan_parquet(url)
            .select(["id", "title", "organization", "matched_locations"])
            .limit(remaining)
            .collect()
        )
        for row in frame.iter_rows(named=True):
            title = str(row.get("title") or "Unknown role")
            organization = str(row.get("organization") or "Unknown")
            source_id = row.get("id")
            skills = _extract_skills_from_text(title)
            category_name = _infer_category(title, skills)
            normalized.append(
                {
                    "source": "hf_7m_jobs",
                    "source_job_id": str(source_id),
                    "title": title,
                    "long_description": None,
                    "company_name": organization,
                    "category_slug": _slugify(category_name),
                    "category_name": category_name,
                    "experience": _infer_experience_years(title, None, skills),
                    "published": _synthetic_published_from_id(source_id),
                    "public_salary_min": None,
                    "public_salary_max": None,
                    "avg_salary": None,
                    "skills": skills,
                    "domain": _parse_first_location(row.get("matched_locations")),
                }
            )
        remaining -= len(frame)

    return normalized


def _fetch_hf_linkedin_records() -> list[dict]:
    settings = get_settings()
    if not settings.hf_linkedin_enabled or settings.hf_linkedin_limit <= 0 or pl is None:
        return []

    frame = (
        pl.scan_parquet(HF_LINKEDIN_PARQUET_URL)
        .select(
            [
                "job_id",
                "company_id",
                "title",
                "description",
                "min_salary",
                "max_salary",
                "med_salary",
                "location",
                "listed_time",
                "original_listed_time",
                "formatted_experience_level",
                "skills_desc",
                "posting_domain",
            ]
        )
        .limit(int(settings.hf_linkedin_limit))
        .collect()
    )

    normalized: list[dict] = []
    for row in frame.iter_rows(named=True):
        title = str(row.get("title") or "Unknown role")
        description = row.get("description")
        structured_skills = _parse_skills(row.get("skills_desc"))
        extracted_skills = _extract_skills_from_text(title, description, row.get("skills_desc"))
        skills = sorted(set(structured_skills + extracted_skills))

        raw_experience = row.get("formatted_experience_level")
        experience_text = f"{title} {raw_experience or ''}"
        category_name = _infer_category(title, skills)
        salary_min = _safe_float(row.get("min_salary"))
        salary_max = _safe_float(row.get("max_salary"))
        salary_med = _safe_float(row.get("med_salary"))
        if salary_min is None and salary_med is not None:
            salary_min = salary_med
        if salary_max is None and salary_med is not None:
            salary_max = salary_med
        avg_salary = (
            salary_med
            if salary_med is not None
            else ((salary_min + salary_max) / 2 if salary_min is not None and salary_max is not None else None)
        )
        company_id = row.get("company_id")
        company_name = f"LinkedIn Company {int(company_id)}" if company_id is not None and not pd.isna(company_id) else "LinkedIn Company"
        published = _safe_datetime_from_epoch(row.get("listed_time")) or _safe_datetime_from_epoch(row.get("original_listed_time"))
        normalized.append(
            {
                "source": "hf_linkedin_jobs",
                "source_job_id": str(row.get("job_id")),
                "title": title,
                "long_description": description,
                "company_name": company_name,
                "category_slug": _slugify(category_name),
                "category_name": category_name,
                "experience": _infer_experience_years(experience_text, description, skills),
                "published": published or datetime.utcnow(),
                "public_salary_min": salary_min,
                "public_salary_max": salary_max,
                "avg_salary": avg_salary,
                "skills": skills,
                "domain": row.get("location") or row.get("posting_domain"),
            }
        )

    return normalized


def _fetch_adzuna_records() -> list[dict]:
    settings = get_settings()
    if not settings.adzuna_enabled or not settings.adzuna_app_id or not settings.adzuna_app_key:
        return []

    endpoint = (
        f"{settings.adzuna_api_url}/{settings.adzuna_country}/search/1"
        f"?app_id={settings.adzuna_app_id}&app_key={settings.adzuna_app_key}"
        f"&results_per_page={settings.adzuna_results_per_page}&what=software"
    )
    with httpx.Client(timeout=30) as client:
        response = client.get(endpoint)
        response.raise_for_status()
        payload = response.json()

    jobs = payload.get("results", [])
    normalized = []
    for job in jobs:
        category_name = str((job.get("category") or {}).get("label") or "Software")
        category_slug = _slugify(category_name)
        company_name = str((job.get("company") or {}).get("display_name") or "Unknown")
        salary_min = _safe_float(job.get("salary_min"))
        salary_max = _safe_float(job.get("salary_max"))
        normalized.append(
            {
                "source": "adzuna",
                "source_job_id": str(job.get("id")),
                "title": str(job.get("title") or "Unknown role"),
                "long_description": job.get("description"),
                "company_name": company_name,
                "category_slug": category_slug,
                "category_name": category_name,
                "experience": 0,
                "published": _safe_datetime(job.get("created")) or datetime.utcnow(),
                "public_salary_min": salary_min,
                "public_salary_max": salary_max,
                "avg_salary": (
                    ((salary_min or 0.0) + (salary_max or 0.0)) / 2
                    if salary_min is not None and salary_max is not None
                    else None
                ),
                "skills": [],
                "domain": str(job.get("location", {}).get("display_name") or ""),
            }
        )
    return normalized


def _get_or_create_category(session: Session, cache: dict[str, Category], slug: str, name: str) -> Category:
    key = f"{slug}:{name}".lower()
    cached = cache.get(key)
    if cached:
        return cached
    existing = session.execute(
        select(Category).where((Category.slug == slug) | (Category.name == name))
    ).scalar_one_or_none()
    if existing:
        if not existing.slug:
            existing.slug = slug
        cache[key] = existing
        return existing

    category = Category(slug=slug, name=name)
    session.add(category)
    session.flush()
    cache[key] = category
    return category


def _get_or_create_company(session: Session, cache: dict[str, Company], name: str) -> Company:
    normalized_name = (name or "Unknown").strip() or "Unknown"
    key = normalized_name.lower()
    cached = cache.get(key)
    if cached:
        return cached
    existing = session.execute(
        select(Company).where(Company.name == normalized_name)
    ).scalar_one_or_none()
    if existing:
        cache[key] = existing
        return existing

    company = Company(name=normalized_name)
    session.add(company)
    session.flush()
    cache[key] = company
    return company


def _get_or_create_skill(session: Session, cache: dict[str, Skill], name: str) -> Skill:
    normalized_name = (name or "").strip()
    key = normalized_name.lower()
    if not key:
        raise ValueError("Skill name is empty")
    cached = cache.get(key)
    if cached:
        return cached
    existing = session.execute(select(Skill).where(Skill.name == normalized_name)).scalar_one_or_none()
    if existing:
        cache[key] = existing
        return existing

    skill = Skill(name=normalized_name)
    session.add(skill)
    session.flush()
    cache[key] = skill
    return skill


def ingest_records(session: Session, source_name: str, records: list[dict]) -> dict:
    run = IngestionRun(
        source=source_name,
        status="running",
        records_seen=0,
        records_upserted=0,
    )
    session.add(run)
    session.flush()

    category_cache: dict[str, Category] = {}
    company_cache: dict[str, Company] = {}
    skill_cache: dict[str, Skill] = {}
    seen_source_ids: set[str] = set()

    try:
        for record in records:
            run.records_seen += 1
            source_job_id = str(record.get("source_job_id") or "").strip()
            if not source_job_id:
                continue
            if source_job_id in seen_source_ids:
                continue
            seen_source_ids.add(source_job_id)
            existing_vacancy = session.execute(
                select(Vacancy).where(
                    Vacancy.source == source_name,
                    Vacancy.source_job_id == source_job_id,
                )
            ).scalar_one_or_none()

            category = _get_or_create_category(
                session=session,
                cache=category_cache,
                slug=str(record.get("category_slug") or "unknown"),
                name=str(record.get("category_name") or "Unknown"),
            )
            company = _get_or_create_company(
                session=session,
                cache=company_cache,
                name=str(record.get("company_name") or "Unknown"),
            )

            salary_min = _safe_float(record.get("public_salary_min"))
            salary_max = _safe_float(record.get("public_salary_max"))
            avg_salary = _safe_float(record.get("avg_salary"))
            if avg_salary is None and salary_min is not None and salary_max is not None:
                avg_salary = (salary_min + salary_max) / 2
            vacancy = existing_vacancy
            if vacancy is None:
                vacancy = Vacancy(
                    source=source_name,
                    source_job_id=source_job_id,
                    title="Unknown role",
                    published=datetime.utcnow(),
                )
                session.add(vacancy)

            vacancy.title = str(record.get("title") or "Unknown role")
            vacancy.long_description = record.get("long_description")
            vacancy.domain = record.get("domain")
            vacancy.experience = _safe_int(record.get("experience"), default=0)
            vacancy.published = _safe_datetime(record.get("published")) or vacancy.published or datetime.utcnow()
            vacancy.public_salary_min = salary_min
            vacancy.public_salary_max = salary_max
            vacancy.avg_salary = avg_salary
            vacancy.category = category
            vacancy.company = company
            vacancy.is_active = True

            skill_entities = []
            for skill_name in record.get("skills", []):
                skill_name = str(skill_name).strip()
                if not skill_name:
                    continue
                skill_entities.append(_get_or_create_skill(session, skill_cache, skill_name))
            vacancy.skills = skill_entities

            run.records_upserted += 1

        run.status = "success"
        run.message = f"Processed {run.records_upserted} records."
        run.finished_at = datetime.utcnow()
        session.commit()
    except Exception as exc:
        session.rollback()
        run.status = "failed"
        run.message = str(exc)
        run.finished_at = datetime.utcnow()
        session.add(run)
        session.commit()
        raise

    return {
        "source": source_name,
        "status": run.status,
        "records_seen": run.records_seen,
        "records_upserted": run.records_upserted,
    }


def run_ingestion_pipeline(session: Session, force_csv: bool = False) -> dict:
    settings = get_settings()
    results = []
    remote_upserted = 0
    errors = []

    if settings.enable_remote_sources and not force_csv:
        try:
            remotive_records = _fetch_remotive_records()
            if remotive_records:
                remotive_result = ingest_records(session, "remotive", remotive_records)
                results.append(remotive_result)
                remote_upserted += remotive_result["records_upserted"]
        except Exception as exc:
            errors.append(f"remotive: {exc}")

        try:
            adzuna_records = _fetch_adzuna_records()
            if adzuna_records:
                adzuna_result = ingest_records(session, "adzuna", adzuna_records)
                results.append(adzuna_result)
                remote_upserted += adzuna_result["records_upserted"]
        except Exception as exc:
            errors.append(f"adzuna: {exc}")

        try:
            arbeitnow_records = _fetch_arbeitnow_records()
            if arbeitnow_records:
                arbeitnow_result = ingest_records(session, "arbeitnow", arbeitnow_records)
                results.append(arbeitnow_result)
                remote_upserted += arbeitnow_result["records_upserted"]
        except Exception as exc:
            errors.append(f"arbeitnow: {exc}")

        try:
            remoteok_records = _fetch_remoteok_records()
            if remoteok_records:
                remoteok_result = ingest_records(session, "remoteok", remoteok_records)
                results.append(remoteok_result)
                remote_upserted += remoteok_result["records_upserted"]
        except Exception as exc:
            errors.append(f"remoteok: {exc}")

        try:
            linkedin_records = _fetch_hf_linkedin_records()
            if linkedin_records:
                linkedin_result = ingest_records(session, "hf_linkedin_jobs", linkedin_records)
                results.append(linkedin_result)
                remote_upserted += linkedin_result["records_upserted"]
        except Exception as exc:
            errors.append(f"hf_linkedin_jobs: {exc}")

        try:
            hf_7m_records = _fetch_hf_7m_records()
            if hf_7m_records:
                hf_7m_result = ingest_records(session, "hf_7m_jobs", hf_7m_records)
                results.append(hf_7m_result)
                remote_upserted += hf_7m_result["records_upserted"]
        except Exception as exc:
            errors.append(f"hf_7m_jobs: {exc}")

    existing_count = session.execute(select(func.count(Vacancy.id))).scalar_one()
    should_run_csv_fallback = force_csv or (existing_count == 0 and remote_upserted == 0)

    if should_run_csv_fallback:
        csv_records = _normalize_csv_records(settings.csv_fallback_path)
        csv_result = ingest_records(session, "csv_fallback", csv_records)
        results.append(csv_result)

    total_seen = sum(result["records_seen"] for result in results)
    total_upserted = sum(result["records_upserted"] for result in results)
    return {
        "runs": results,
        "total_seen": total_seen,
        "total_upserted": total_upserted,
        "errors": errors,
        "used_csv_fallback": should_run_csv_fallback,
    }
