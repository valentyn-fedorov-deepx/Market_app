import glob
import logging
import math
import os
import time

import numpy as np
import pandas as pd

# Prophet/cmdstanpy are very chatty on fit — keep server logs clean.
logging.getLogger("prophet").setLevel(logging.WARNING)
logging.getLogger("cmdstanpy").setLevel(logging.WARNING)


def _ensure_cmdstan_path() -> None:
    """Point cmdstanpy at the CmdStan bundled inside the prophet wheel.

    Prophet ships a precompiled model plus a CmdStan tree under
    `prophet/stan_model/cmdstan-*`, but cmdstanpy only looks in ~/.cmdstan.
    Wiring CMDSTAN here lets Prophet run with no separate CmdStan install
    (Windows dev boxes, slim Docker images, etc.).
    """
    if os.environ.get("CMDSTAN"):
        return
    try:
        import prophet as _prophet_pkg

        bundled = sorted(glob.glob(os.path.join(os.path.dirname(_prophet_pkg.__file__), "stan_model", "cmdstan-*")))
        bundled = [path for path in bundled if os.path.isdir(path)]
        if bundled:
            path = bundled[-1]
            os.environ["CMDSTAN"] = path
            # The wheel-bundled CmdStan ships a precompiled model but no makefile;
            # cmdstanpy's path validation requires one, so drop an empty stub.
            makefile = os.path.join(path, "makefile")
            if not os.path.exists(makefile):
                try:
                    open(makefile, "a").close()
                except OSError:
                    pass
    except Exception:
        pass


_ensure_cmdstan_path()


def _clean_series(series: pd.Series) -> pd.Series:
    """Replace NaN/Inf with 0 so the values are JSON-serializable."""
    return series.replace([np.inf, -np.inf], np.nan).fillna(0.0)


def _finite_or_none(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None

try:
    from prophet import Prophet
except Exception:  # pragma: no cover
    Prophet = None


# Models that express seasonality/curvature are preferred when their accuracy is
# within MODEL_SELECTION_TOLERANCE of the best backtest score. This keeps the
# forecast curve dynamic (seasonal ups/downs) instead of collapsing to a straight
# line, while never picking a model that is meaningfully worse on the holdout set.
MODEL_PRIORITY = {
    "prophet": 3,
    "seasonal_naive": 2,
    "linear_trend": 1,
}
MODEL_SELECTION_TOLERANCE = 0.15

# Accept a few human-friendly aliases for the explicit model choice.
MODEL_ALIASES = {
    "auto": "auto",
    "prophet": "prophet",
    "linear": "linear_trend",
    "linear_trend": "linear_trend",
    "trend": "linear_trend",
    "seasonal_naive": "seasonal_naive",
    "naive": "seasonal_naive",
    "seasonal": "seasonal_naive",
}

# Sources whose dates do NOT form a real temporal distribution must not drive the
# time-series (they would create artificial spikes/flatlines). They still feed
# volume/skills/salary analytics — just not seasonality/forecasting.
#   - hf_7m_jobs:       ships without any timestamp column (dates imputed)
#   - hf_linkedin_jobs: a single 2-day scrape snapshot (all rows in one month)
NON_TEMPORAL_SOURCES = {"hf_7m_jobs", "hf_linkedin_jobs"}

# Forecasts (especially Prophet's CmdStan fit) are expensive, so cache results
# keyed by the series fingerprint. Cleared implicitly when data changes (the
# fingerprint includes row count + sum, which shift after every ingestion).
_FORECAST_CACHE: dict = {}
_FORECAST_CACHE_MAX = 128


class MarketForecasterAdvanced:
    def __init__(self, df: pd.DataFrame):
        self.df = df.sort_values("published").copy()
        # Populated by each model fn with its learned parameters (proof of fit).
        self._last_meta: dict = {}

    @staticmethod
    def _to_forecast_dict(forecast: pd.DataFrame, ts_data: pd.DataFrame, model_name: str, backtest: dict) -> dict:
        hist = _clean_series(ts_data["y"])
        hist_max = float(hist.max()) if len(hist) else 0.0
        # Defensive cap: keep an explosive extrapolation from blowing up the
        # y-axis and flattening the real data range on the chart.
        cap = max(hist_max * 2.5, 10.0)
        return {
            "model_used": model_name,
            "backtest": {"mae": _finite_or_none(backtest.get("mae")), "mape": _finite_or_none(backtest.get("mape"))},
            "dates": forecast["ds"].dt.strftime("%Y-%m-%d").tolist(),
            "predicted_demand": _clean_series(forecast["yhat"]).round(2).clip(lower=0, upper=cap).tolist(),
            "confidence_upper": _clean_series(forecast["yhat_upper"]).round(2).clip(lower=0, upper=cap).tolist(),
            "confidence_lower": _clean_series(forecast["yhat_lower"]).round(2).clip(lower=0, upper=cap).tolist(),
            "historical_dates": ts_data["ds"].dt.strftime("%Y-%m-%d").tolist(),
            "historical_demand": hist.tolist(),
        }

    @staticmethod
    def _seasonal_periods(freq: str) -> int:
        return 7 if freq == "D" else 12

    def _prepare_series(self, category_name: str, freq: str) -> pd.DataFrame:
        scoped = self.df[self.df["category_name"] == category_name]
        if scoped.empty:
            return pd.DataFrame(columns=["ds", "y"])

        # Keep only sources with a real temporal distribution so seasonality is
        # genuine. Fall back to the full set if the temporal subset is too small.
        if "source" in scoped.columns:
            temporal = scoped[~scoped["source"].isin(NON_TEMPORAL_SOURCES)]
            if len(temporal) >= 10:
                scoped = temporal

        demand = scoped.groupby(pd.Grouper(key="published", freq=freq)).size()
        full_index = pd.date_range(start=demand.index.min(), end=demand.index.max(), freq=freq)
        demand = demand.reindex(full_index, fill_value=0)
        ts_data = demand.reset_index(name="y").rename(columns={"index": "ds"})
        return ts_data

    def _feasible_models(self, ts_data: pd.DataFrame, freq: str) -> list[str]:
        """Models that can actually run on this series, in priority order."""
        n = len(ts_data)
        sp = self._seasonal_periods(freq)
        feasible = []
        if Prophet is not None and n >= 10:
            feasible.append("prophet")
        if n >= 14 and n >= sp:
            feasible.append("seasonal_naive")
        if n >= 3:
            feasible.append("linear_trend")
        return feasible

    def _prophet_forecast(self, ts_data: pd.DataFrame, periods: int, freq: str) -> pd.DataFrame | None:
        self._last_meta = {}
        if len(ts_data) < 10 or Prophet is None:
            return None
        try:
            model = Prophet(
                yearly_seasonality=True,
                weekly_seasonality=(freq == "D"),
                daily_seasonality=False,
                seasonality_mode="multiplicative",
                changepoint_prior_scale=0.1,
                n_changepoints=10,
                mcmc_samples=0,
            )
            model.fit(ts_data[["ds", "y"]])
            future = model.make_future_dataframe(periods=periods, freq=freq)
            forecast = model.predict(future)[["ds", "yhat", "yhat_lower", "yhat_upper"]]
            self._last_meta = {
                "changepoints": int(len(model.changepoints)),
                "seasonality_mode": "multiplicative",
            }
            return forecast
        except Exception:
            return None

    def _linear_forecast(self, ts_data: pd.DataFrame, periods: int, freq: str) -> pd.DataFrame | None:
        self._last_meta = {}
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

        self._last_meta = {"slope": round(float(slope), 4), "intercept": round(float(intercept), 2)}

        full_dates = pd.date_range(start=ts_data["ds"].iloc[0], periods=total_len, freq=freq)
        return pd.DataFrame(
            {
                "ds": full_dates,
                "yhat": yhat,
                "yhat_lower": yhat - (1.96 * sigma),
                "yhat_upper": yhat + (1.96 * sigma),
            }
        )

    def _seasonal_naive_forecast(self, ts_data: pd.DataFrame, periods: int, freq: str) -> pd.DataFrame | None:
        self._last_meta = {}
        if len(ts_data) < 14:
            return None

        seasonal_period = self._seasonal_periods(freq)
        y_hist = ts_data["y"].to_numpy(dtype=float)
        if len(y_hist) < seasonal_period:
            return None

        repeated = np.resize(y_hist[-seasonal_period:], periods)
        yhat = np.concatenate([y_hist, repeated])
        sigma = max(float(np.std(y_hist)) * 0.2, 1.0)

        self._last_meta = {"season_length": int(seasonal_period)}

        full_dates = pd.date_range(start=ts_data["ds"].iloc[0], periods=len(ts_data) + periods, freq=freq)
        return pd.DataFrame(
            {
                "ds": full_dates,
                "yhat": yhat,
                "yhat_lower": yhat - (1.96 * sigma),
                "yhat_upper": yhat + (1.96 * sigma),
            }
        )

    def _backtest(self, ts_data: pd.DataFrame, model_fn, freq: str) -> dict:
        """Train on all-but-last-N, predict the held-out tail, score vs actual."""
        out = {"mae": None, "mape": None, "test_size": 0, "holdout": None}
        if len(ts_data) < 30:
            return out

        test_size = max(7, min(30, len(ts_data) // 5))
        train = ts_data.iloc[:-test_size].copy()
        test = ts_data.iloc[-test_size:].copy()
        forecast = model_fn(train, test_size, freq)
        if forecast is None or len(forecast) < test_size:
            return out

        raw_pred = forecast["yhat"].tail(test_size).to_numpy(dtype=float)
        predicted = np.nan_to_num(raw_pred, nan=0.0, posinf=0.0, neginf=0.0).clip(min=0)
        actual = test["y"].to_numpy(dtype=float)

        mae = _finite_or_none(np.mean(np.abs(actual - predicted)))
        non_zero = actual != 0
        mape = _finite_or_none(np.mean(np.abs((actual[non_zero] - predicted[non_zero]) / actual[non_zero])) * 100) if np.any(non_zero) else None
        if mae is None:
            return out

        out["mae"] = round(mae, 3)
        out["mape"] = round(mape, 3) if mape is not None else None
        out["test_size"] = int(test_size)
        out["holdout"] = {
            "dates": test["ds"].dt.strftime("%Y-%m-%d").tolist(),
            "actual": [round(float(v), 2) for v in actual],
            "predicted": [round(float(v), 2) for v in predicted],
        }
        return out

    @staticmethod
    def _score(backtest: dict) -> float:
        mae = backtest["mae"]
        mape = backtest["mape"] if backtest["mape"] is not None else 10_000
        return (mae if mae is not None else 10_000) + (mape / 100)

    def get_prophet_forecast(self, category_name: str, periods: int, freq: str = "MS", model: str | None = None) -> dict | None:
        ts_data = self._prepare_series(category_name, freq=freq)
        if len(ts_data) < 10:
            return None

        requested = MODEL_ALIASES.get((model or "auto").strip().lower(), "auto")
        cache_key = (category_name, int(periods), freq, requested, len(ts_data), round(float(ts_data["y"].sum()), 2))
        cached = _FORECAST_CACHE.get(cache_key)
        if cached is not None:
            return cached

        fn_map = {
            "prophet": self._prophet_forecast,
            "seasonal_naive": self._seasonal_naive_forecast,
            "linear_trend": self._linear_forecast,
        }

        available = self._feasible_models(ts_data, freq)
        if not available:
            return None

        forced = requested != "auto" and requested in available
        fallback = requested != "auto" and requested not in available
        to_eval = [requested] if forced else available

        evaluated = []
        for name in to_eval:
            fn = fn_map[name]
            start = time.perf_counter()
            forecast = fn(ts_data, periods, freq)
            train_ms = round((time.perf_counter() - start) * 1000, 1)
            if forecast is None:
                continue
            meta = dict(self._last_meta)
            backtest = self._backtest(ts_data, fn, freq=freq)
            evaluated.append(
                {
                    "name": name,
                    "forecast": forecast,
                    "backtest": backtest,
                    "score": self._score(backtest),
                    "train_ms": train_ms,
                    "meta": meta,
                }
            )

        if not evaluated:
            return None

        if forced:
            chosen = evaluated[0]
        else:
            best_score = min(item["score"] for item in evaluated)
            threshold = best_score * (1.0 + MODEL_SELECTION_TOLERANCE) + 1e-9
            within_tolerance = [item for item in evaluated if item["score"] <= threshold]
            chosen = max(within_tolerance, key=lambda item: MODEL_PRIORITY.get(item["name"], 0))

        result = self._to_forecast_dict(
            chosen["forecast"],
            ts_data,
            model_name=chosen["name"],
            backtest=chosen["backtest"],
        )
        result["available_models"] = available
        result["requested_model"] = requested
        result["fallback"] = fallback
        result["training"] = {
            "samples": int(len(ts_data)),
            "train_time_ms": chosen["train_ms"],
            "freq": freq,
            "backtest": {
                "mae": chosen["backtest"].get("mae"),
                "mape": chosen["backtest"].get("mape"),
                "test_size": chosen["backtest"].get("test_size"),
            },
            "holdout": chosen["backtest"].get("holdout"),
            "diagnostics": chosen["meta"],
        }

        _FORECAST_CACHE[cache_key] = result
        if len(_FORECAST_CACHE) > _FORECAST_CACHE_MAX:
            _FORECAST_CACHE.pop(next(iter(_FORECAST_CACHE)))
        return result
