import ast
import pandas as pd


QUARTILE_LABELS = ['Q1 (Lowest)', 'Q2', 'Q3', 'Q4 (Top)']


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

    result = _add_salary_quartiles(result)
    return result


def load_and_prepare_data(data_path: str) -> pd.DataFrame:
    df = pd.read_csv(data_path)
    return prepare_dataframe(df)
