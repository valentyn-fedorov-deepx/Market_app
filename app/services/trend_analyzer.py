import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression


class TrendAnalyzer:
    def calculate_trends(self, df: pd.DataFrame, column: str, period: str = 'W') -> list:
        if column == 'skills':
            df_exploded = df.explode('skills').rename(columns={'skills': 'item'})
        else:
            df_exploded = df.rename(columns={column: 'item'})

        df_exploded.dropna(subset=['item'], inplace=True)

        trends = df_exploded.groupby([pd.Grouper(key='published', freq=period), 'item']).size().reset_index(
            name='count')

        results = []
        for item_name, group in trends.groupby('item'):
            if len(group) < 3: continue
            X = np.array(range(len(group))).reshape(-1, 1)
            y = group['count'].values
            model = LinearRegression().fit(X, y)
            results.append({'item': item_name, 'trend_slope': model.coef_[0]})

        if not results: return []

        return pd.DataFrame(results).sort_values('trend_slope', ascending=False).to_dict(orient='records')