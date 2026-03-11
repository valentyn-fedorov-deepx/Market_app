from collections import Counter
from typing import List, Optional
from fastapi import APIRouter, Query, Request
import pandas as pd

router = APIRouter()

def _normalize_skills(skills: Optional[List[str]]) -> list[str]:
    return [skill.strip() for skill in (skills or []) if skill and skill.strip()]


def _apply_skills_filter(df: pd.DataFrame, skills: list[str]) -> pd.DataFrame:
    required = {skill.lower() for skill in skills}
    if not required:
        return df
    return df[
        df["skills"].apply(
            lambda row: required.issubset({str(skill).strip().lower() for skill in (row or [])})
        )
    ]


@router.get("/options")
def get_filter_options(
        request: Request,
        category: Optional[str] = None,
        experience_min: Optional[int] = None,
        skills: Optional[List[str]] = Query(None),
):
    """Повертає списки унікальних значень для фільтрів."""
    main_df = request.app.state.main_df
    required_columns = {"category_name", "skills", "experience"}
    if main_df is None or main_df.empty or not required_columns.issubset(set(main_df.columns)):
        return {
            "categories": [],
            "skills": [],
            "experience_range": {"min": 0, "max": 0},
            "experience_values": [0],
        }

    selected_skills = _normalize_skills(skills)
    selected_category = category.strip() if category and category.strip() else None

    # Categories respond to all filters except category itself.
    categories_df = main_df
    if experience_min is not None:
        categories_df = categories_df[categories_df["experience"] >= experience_min]
    categories_df = _apply_skills_filter(categories_df, selected_skills)
    category_counts = categories_df["category_name"].value_counts()
    categories = sorted(
        category_counts.index.tolist(),
        key=lambda name: (-int(category_counts[name]), name.lower()),
    )

    if selected_category and selected_category not in categories:
        selected_category = None

    # Skills respond to category + experience filters.
    skills_df = main_df
    if selected_category:
        skills_df = skills_df[skills_df["category_name"] == selected_category]
    if experience_min is not None:
        skills_df = skills_df[skills_df["experience"] >= experience_min]
    skill_counter: Counter[str] = Counter()
    for skill_list in skills_df["skills"].tolist():
        for skill in (skill_list or []):
            normalized = str(skill).strip()
            if normalized:
                skill_counter[normalized] += 1
    all_skills = [skill for skill, _ in sorted(skill_counter.items(), key=lambda item: (-item[1], item[0].lower()))]

    # Experience responds to category + selected skills filters.
    experience_df = main_df
    if selected_category:
        experience_df = experience_df[experience_df["category_name"] == selected_category]
    experience_df = _apply_skills_filter(experience_df, selected_skills)
    if experience_df.empty:
        exp_values = [0]
    else:
        exp_values = sorted({int(value) for value in experience_df["experience"].dropna().tolist()})
        if not exp_values:
            exp_values = [0]
    exp_min = int(min(exp_values))
    exp_max = int(max(exp_values))

    return {
        "categories": categories,
        "skills": all_skills,
        "experience_range": {"min": exp_min, "max": exp_max},
        "experience_values": exp_values,
    }