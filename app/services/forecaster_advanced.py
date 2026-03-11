import numpy as np
import pandas as pd
try:
    from prophet import Prophet
except Exception:  # pragma: no cover
    Prophet = None


class MarketForecasterAdvanced:
    def __init__(self, df: pd.DataFrame):
        self.df = df.sort_values("published").copy()

    @staticmethod
    def _to_forecast_dict(forecast: pd.DataFrame, ts_data: pd.DataFrame, model_name: str, backtest: dict) -> dict:
        return {
            "model_used": model_name,
            "backtest": backtest,
            "dates": forecast["ds"].dt.strftime("%Y-%m-%d").tolist(),
            "predicted_demand": forecast["yhat"].round(2).clip(lower=0).tolist(),
            "confidence_upper": forecast["yhat_upper"].round(2).clip(lower=0).tolist(),
            "confidence_lower": forecast["yhat_lower"].round(2).clip(lower=0).tolist(),
            "historical_dates": ts_data["ds"].dt.strftime("%Y-%m-%d").tolist(),
            "historical_demand": ts_data["y"].tolist(),
        }

    def _prepare_series(self, category_name: str, freq: str) -> pd.DataFrame:
        scoped = self.df[self.df["category_name"] == category_name]
        if scoped.empty:
            return pd.DataFrame(columns=["ds", "y"])

        demand = scoped.groupby(pd.Grouper(key="published", freq=freq)).size()
        full_index = pd.date_range(start=demand.index.min(), end=demand.index.max(), freq=freq)
        demand = demand.reindex(full_index, fill_value=0)
        ts_data = demand.reset_index(name="y").rename(columns={"index": "ds"})
        return ts_data

    def _prophet_forecast(self, ts_data: pd.DataFrame, periods: int, freq: str) -> pd.DataFrame | None:
        if len(ts_data) < 10 or Prophet is None:
            return None
        try:
            model = Prophet(yearly_seasonality=True, weekly_seasonality=(freq == "D"), daily_seasonality=False)
            model.fit(ts_data[["ds", "y"]])
            future = model.make_future_dataframe(periods=periods, freq=freq)
            forecast = model.predict(future)[["ds", "yhat", "yhat_lower", "yhat_upper"]]
            return forecast
        except Exception:
            return None

    @staticmethod
    def _linear_forecast(ts_data: pd.DataFrame, periods: int, freq: str) -> pd.DataFrame | None:
        if len(ts_data) < 3:
            return None

        x_hist = np.arange(len(ts_data))
        y_hist = ts_data["y"].to_numpy(dtype=float)
        slope, intercept = np.polyfit(x_hist, y_hist, 1)

        total_len = len(ts_data) + periods
        x_full = np.arange(total_len)
        yhat = (slope * x_full) + intercept

        residuals = y_hist - ((slope * x_hist) + intercept)
        sigma = float(np.std(residuals)) if len(residuals) > 2 else max(float(np.std(y_hist)) * 0.15, 1.0)

        full_dates = pd.date_range(start=ts_data["ds"].iloc[0], periods=total_len, freq=freq)
        forecast = pd.DataFrame(
            {
                "ds": full_dates,
                "yhat": yhat,
                "yhat_lower": yhat - (1.96 * sigma),
                "yhat_upper": yhat + (1.96 * sigma),
            }
        )
        return forecast

    @staticmethod
    def _seasonal_naive_forecast(ts_data: pd.DataFrame, periods: int, freq: str) -> pd.DataFrame | None:
        if len(ts_data) < 14:
            return None

        seasonal_period = 7 if freq == "D" else 12
        y_hist = ts_data["y"].to_numpy(dtype=float)
        if len(y_hist) < seasonal_period:
            return None

        repeated = np.resize(y_hist[-seasonal_period:], periods)
        yhat = np.concatenate([y_hist, repeated])
        sigma = max(float(np.std(y_hist)) * 0.2, 1.0)

        full_dates = pd.date_range(start=ts_data["ds"].iloc[0], periods=len(ts_data) + periods, freq=freq)
        forecast = pd.DataFrame(
            {
                "ds": full_dates,
                "yhat": yhat,
                "yhat_lower": yhat - (1.96 * sigma),
                "yhat_upper": yhat + (1.96 * sigma),
            }
        )
        return forecast

    def _evaluate_model(self, ts_data: pd.DataFrame, model_fn, freq: str) -> dict:
        if len(ts_data) < 30:
            return {"mae": None, "mape": None}

        test_size = max(7, min(30, len(ts_data) // 5))
        train = ts_data.iloc[:-test_size].copy()
        test = ts_data.iloc[-test_size:].copy()
        forecast = model_fn(train, test_size, freq)

        if forecast is None or len(forecast) < test_size:
            return {"mae": None, "mape": None}

        predicted = forecast["yhat"].tail(test_size).to_numpy(dtype=float)
        actual = test["y"].to_numpy(dtype=float)

        mae = float(np.mean(np.abs(actual - predicted)))
        non_zero = actual != 0
        if np.any(non_zero):
            mape = float(np.mean(np.abs((actual[non_zero] - predicted[non_zero]) / actual[non_zero])) * 100)
        else:
            mape = None
        return {"mae": round(mae, 3), "mape": round(mape, 3) if mape is not None else None}

    def get_prophet_forecast(self, category_name: str, periods: int, freq: str = "D") -> dict | None:
        ts_data = self._prepare_series(category_name, freq=freq)
        if len(ts_data) < 10:
            return None

        candidates = {
            "prophet": self._prophet_forecast,
            "linear_trend": self._linear_forecast,
            "seasonal_naive": self._seasonal_naive_forecast,
        }

        best = None
        best_name = None
        best_backtest = {"mae": None, "mape": None}

        for name, fn in candidates.items():
            forecast = fn(ts_data, periods, freq)
            if forecast is None:
                continue

            backtest = self._evaluate_model(ts_data, fn, freq=freq)
            mae = backtest["mae"]
            mape = backtest["mape"] if backtest["mape"] is not None else 10_000
            score = (mae if mae is not None else 10_000) + (mape / 100)

            if best is None:
                best = forecast
                best_name = name
                best_backtest = backtest
                best_score = score
                continue

            if score < best_score:
                best = forecast
                best_name = name
                best_backtest = backtest
                best_score = score

        if best is None:
            return None

        return self._to_forecast_dict(best, ts_data, model_name=best_name, backtest=best_backtest)
