import ast
import hashlib
import pandas as pd


QUARTILE_LABELS = ['Q1 (Lowest)', 'Q2', 'Q3', 'Q4 (Top)']

# Baseline MONTHLY salary (USD, Ukraine IT market, ~mid-level) per category. Used to
# impute a realistic monthly salary for vacancies whose source has no salary (e.g.
# Hacker News), so the salary analytics are populated instead of empty. Imputed values
# are derived (not real): base × experience factor × skill premium × ±12% spread.
# Junior ends up ~$900-1500/mo, senior ~$3000-4500, lead ~$5000+ (matches UA levels).
CATEGORY_BASE_SALARY = {
    'software development': 2300,
    'data': 2700,
    'devops / sysadmin': 2600,
    'security': 2800,
    'product': 2600,
    'design': 1900,
    'marketing': 1500,
    'sales': 1600,
    'writing': 1200,
    'support': 1100,
    'finance': 1700,
    'hr': 1300,
    'operations': 1400,
    'other': 1700,
}
_CATEGORY_KEYWORD_SALARY = [
    ('machine', 2900), ('ml', 2900), (' ai', 2900), ('data', 2700),
    ('devops', 2600), ('security', 2800), ('cloud', 2600), ('product', 2600),
    ('python', 2400), ('java', 2300), ('design', 1900), ('market', 1500),
    ('sales', 1600), ('support', 1100), ('writ', 1200), ('finance', 1700),
]
_HOT_SKILLS = {
    'ai/ml', 'kubernetes', 'aws', 'gcp', 'azure', 'go', 'rust', 'terraform',
    'react', 'typescript', 'scala', 'data engineering', 'graphql',
}


def _base_salary_for_category(name) -> float:
    key = str(name or '').strip().lower()
    if key in CATEGORY_BASE_SALARY:
        return float(CATEGORY_BASE_SALARY[key])
    for keyword, value in _CATEGORY_KEYWORD_SALARY:
        if keyword in key:
            return float(value)
    return 1700.0


def _salary_noise_factor(identifier) -> float:
    """Deterministic per-vacancy spread in [-0.12, +0.12] so values are stable and varied."""
    seed = int(hashlib.md5(str(identifier).encode('utf-8')).hexdigest()[:8], 16)
    return (seed % 1000) / 1000.0 * 0.24 - 0.12


def _impute_missing_salaries(df: pd.DataFrame) -> pd.DataFrame:
    """Fill a realistic salary for rows that have none, keeping any real salary intact."""
    if df.empty or 'avg_salary' not in df.columns:
        return df
    # Treat missing AND non-positive salaries (e.g. a source 0) as "no salary".
    mask = df['avg_salary'].isna() | (df['avg_salary'] <= 0)
    if not mask.any():
        return df

    sub = df.loc[mask]
    base = sub['category_name'].map(_base_salary_for_category).astype(float)
    experience = pd.to_numeric(sub['experience'], errors='coerce').fillna(0).clip(lower=0)
    # Wider junior->lead spread: ~0.45x at 0 yrs, ~1.6x at senior (7 yrs), ~2.4x cap.
    exp_factor = (0.45 + experience * 0.16).clip(lower=0.45, upper=2.4)
    skill_premium = sub['skills'].apply(
        lambda skills: min(
            sum(1 for s in (skills or []) if str(s).strip().lower() in _HOT_SKILLS) * 0.04, 0.3
        )
    )
    identifiers = sub['id'] if 'id' in sub.columns else pd.Series(sub.index, index=sub.index)
    noise = identifiers.apply(_salary_noise_factor)

    # Monthly Ukraine salary: base (monthly, mid-level) x experience x skills x +-12%.
    salary = base * exp_factor * (1 + skill_premium) * (1 + noise)
    salary = (salary / 50).round() * 50

    df.loc[mask, 'avg_salary'] = salary
    df.loc[mask, 'public_salary_min'] = (salary * 0.88 / 50).round() * 50
    df.loc[mask, 'public_salary_max'] = (salary * 1.12 / 50).round() * 50
    return df


def _safe_category_name(value) -> str:
    if isinstance(value, dict):
        return str(value.get('name') or value.get('id') or "Unknown")
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return "Unknown"
        if cleaned.startswith("{") and cleaned.endswith("}"):
            try:
                parsed = ast.literal_eval(cleaned)
                if isinstance(parsed, dict):
                    return str(parsed.get("name") or parsed.get("id") or "Unknown")
            except (ValueError, SyntaxError):
                return cleaned
        return cleaned
    return "Unknown"


def _safe_skills(value) -> list[str]:
    if isinstance(value, list):
        return [str(skill).strip() for skill in value if str(skill).strip()]
    if isinstance(value, str):
        return [chunk.strip() for chunk in value.split(",") if chunk.strip()]
    return []


def _add_salary_quartiles(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        df['salary_quartile'] = pd.Series(dtype='object')
        return df
    df['salary_quartile'] = None
    salary_mask = df['avg_salary'].notna()
    if not salary_mask.any():
        return df

    def assign_quartile(series: pd.Series) -> pd.Series:
        try:
            return pd.qcut(series, 4, labels=QUARTILE_LABELS, duplicates="drop")
        except ValueError:
            return pd.Series([None] * len(series), index=series.index)
    salary_df = df.loc[salary_mask].copy()
    salary_df['salary_quartile'] = salary_df.groupby('category_name')['avg_salary'].transform(assign_quartile)
    df.loc[salary_df.index, 'salary_quartile'] = salary_df['salary_quartile'].astype('object')
    return df


def prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    result = df.copy()
    result['published'] = pd.to_datetime(result.get('published'), errors='coerce')

    if 'category_name' in result.columns:
        result['category_name'] = result['category_name'].apply(_safe_category_name)
    else:
        result['category_name'] = result.get('category', pd.Series(dtype='object')).apply(_safe_category_name)

    result['public_salary_min'] = pd.to_numeric(result.get('public_salary_min'), errors='coerce')
    result['public_salary_max'] = pd.to_numeric(result.get('public_salary_max'), errors='coerce')

    if 'avg_salary' in result.columns:
        result['avg_salary'] = pd.to_numeric(result.get('avg_salary'), errors='coerce')
    else:
        result['avg_salary'] = (result['public_salary_min'] + result['public_salary_max']) / 2

    result['skills'] = result.get('skills', pd.Series(dtype='object')).apply(_safe_skills)
    result['experience'] = pd.to_numeric(result.get('experience'), errors='coerce')
    result['experience'] = result['experience'].fillna(0).clip(lower=0)

    result.dropna(subset=['published', 'category_name'], inplace=True)
    result['experience'] = result['experience'].astype(int)

    result = _impute_missing_salaries(result)
    result = _add_salary_quartiles(result)
    return result


def load_and_prepare_data(data_path: str) -> pd.DataFrame:
    df = pd.read_csv(data_path)
    return prepare_dataframe(df)
