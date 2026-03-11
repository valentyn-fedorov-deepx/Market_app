import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import MultiLabelBinarizer


class MarketForecaster:
    def __init__(self, df: pd.DataFrame):
        self.df = df

    def analyze_skills(self) -> dict:
        if self.df.empty or 'skills' not in self.df.columns:
            return {}

        df_with_skills = self.df[(self.df['skills'].apply(len) > 0) & (self.df['avg_salary'].notna())]
        if df_with_skills.empty:
            return {}

        mlb = MultiLabelBinarizer()
        X = mlb.fit_transform(df_with_skills['skills'])
        y = df_with_skills['avg_salary']

        # Перевірка на достатню кількість даних для навчання
        if len(y) < 2:
            return {"skill_importance_for_salary": []}

        rf = RandomForestRegressor(n_estimators=50, n_jobs=-1, random_state=42).fit(X, y)
        skill_importance = pd.DataFrame({
            'skill': mlb.classes_,
            'importance': rf.feature_importances_
        }).sort_values('importance', ascending=False).head(15)

        return {"skill_importance_for_salary": skill_importance.to_dict(orient='records')}