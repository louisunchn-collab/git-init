"""销量趋势预测。

设计原则：
- 默认走轻量级方案（移动平均 + 线性回归外推），不依赖 Prophet/statsmodels
  这样任何一台只装了 pandas/sklearn 的机器都能跑
- 如果检测到 prophet 已安装，自动切换到 Prophet（精度更高，能学季节性）

数据要求：
- 一个 DataFrame，至少含两列：date (datetime / str) + sold (数值)
- 同一天可以有多行（不同 SKU），会先按日期聚合

输出：
- 一个 DataFrame，含 date / sold / forecast / yhat_lower / yhat_upper
"""

from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd


def _aggregate_daily(df: pd.DataFrame) -> pd.DataFrame:
    daily = (
        df.assign(date=pd.to_datetime(df["date"], errors="coerce"))
        .dropna(subset=["date"])
        .groupby("date", as_index=False)["sold"]
        .sum()
        .sort_values("date")
    )
    return daily


def forecast_sold(
    df: pd.DataFrame,
    horizon_days: int = 30,
    method: Literal["auto", "ma", "prophet"] = "auto",
) -> pd.DataFrame:
    """对销量做 horizon_days 天预测。

    method='auto'：检测到 prophet 就用 prophet，否则降级移动平均 + 线性外推。
    """
    daily = _aggregate_daily(df)
    if daily.empty or len(daily) < 3:
        return pd.DataFrame(columns=["date", "sold", "forecast", "yhat_lower", "yhat_upper"])

    if method == "auto":
        try:
            import prophet  # noqa: F401
            method = "prophet"
        except ImportError:
            method = "ma"

    if method == "prophet":
        return _forecast_prophet(daily, horizon_days)
    return _forecast_simple(daily, horizon_days)


# ---------------------------------------------------------------------------
# 轻量级方案
# ---------------------------------------------------------------------------

def _forecast_simple(daily: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """7 日移动平均做平滑 + 线性回归外推 + 经验置信区间。"""
    daily = daily.copy()
    daily["forecast"] = daily["sold"].rolling(window=7, min_periods=1).mean()

    # 用最近 30 天做趋势线性回归
    recent = daily.tail(30).reset_index(drop=True)
    x = np.arange(len(recent), dtype=float)
    y = recent["sold"].to_numpy(dtype=float)
    if len(recent) >= 2 and np.std(x) > 0:
        slope, intercept = np.polyfit(x, y, 1)
    else:
        slope, intercept = 0.0, float(y.mean()) if len(y) else 0.0

    # 未来 horizon 天
    last_date = daily["date"].max()
    future_dates = pd.date_range(
        start=last_date + pd.Timedelta(days=1), periods=horizon, freq="D"
    )
    last_x = len(recent) - 1
    future_y = np.array(
        [max(0.0, intercept + slope * (last_x + i + 1)) for i in range(horizon)]
    )

    # 经验置信区间：用最近 14 天残差标准差
    sigma = float(daily["sold"].tail(14).std() or 0.0)
    upper = future_y + 1.5 * sigma
    lower = np.clip(future_y - 1.5 * sigma, 0, None)

    future_df = pd.DataFrame(
        {
            "date": future_dates,
            "sold": np.nan,
            "forecast": future_y,
            "yhat_lower": lower,
            "yhat_upper": upper,
        }
    )

    history_df = daily.assign(yhat_lower=np.nan, yhat_upper=np.nan)
    return pd.concat([history_df, future_df], ignore_index=True)


# ---------------------------------------------------------------------------
# Prophet 方案（可选）
# ---------------------------------------------------------------------------

def _forecast_prophet(daily: pd.DataFrame, horizon: int) -> pd.DataFrame:
    from prophet import Prophet

    m = Prophet(
        weekly_seasonality=True,
        yearly_seasonality=len(daily) >= 365,
        daily_seasonality=False,
    )
    train = daily.rename(columns={"date": "ds", "sold": "y"})
    m.fit(train)

    future = m.make_future_dataframe(periods=horizon, freq="D")
    fc = m.predict(future)
    fc = fc[["ds", "yhat", "yhat_lower", "yhat_upper"]].rename(
        columns={"ds": "date", "yhat": "forecast"}
    )

    out = fc.merge(daily, on="date", how="left")
    return out[["date", "sold", "forecast", "yhat_lower", "yhat_upper"]]


# ---------------------------------------------------------------------------
# 类目级爆款潜力评估（单期数据下的启发式版本）
# ---------------------------------------------------------------------------

def category_trend_signal(df: pd.DataFrame) -> pd.DataFrame:
    """如果有多期 (多天) 数据，按类目计算环比增长率。

    输出：
        category | sold_curr | sold_prev | growth_% | trend
    """
    if df.empty or "category" not in df.columns:
        return pd.DataFrame()

    dates = pd.to_datetime(df["date"], errors="coerce")
    if dates.nunique() < 2:
        return pd.DataFrame()

    df = df.assign(date=dates).dropna(subset=["date"])
    pivot = (
        df.groupby(["category", "date"])["sold"]
        .sum()
        .reset_index()
        .sort_values("date")
    )
    last_two = pivot["date"].drop_duplicates().nlargest(2).tolist()
    if len(last_two) < 2:
        return pd.DataFrame()
    d_curr, d_prev = last_two[0], last_two[1]

    curr = pivot[pivot["date"] == d_curr].set_index("category")["sold"]
    prev = pivot[pivot["date"] == d_prev].set_index("category")["sold"]

    out = pd.DataFrame({"sold_curr": curr, "sold_prev": prev}).fillna(0)
    out["growth_%"] = ((out["sold_curr"] - out["sold_prev"]) / out["sold_prev"].replace(0, np.nan) * 100).round(2)
    out["trend"] = out["growth_%"].apply(
        lambda g: "🚀 强增长" if g >= 30 else "📈 增长" if g > 0 else "📉 下滑" if g < 0 else "—"
    )
    return out.reset_index().sort_values("growth_%", ascending=False)
