"""核心业务分析。

提供四个最关键的视角：
1. price_band_summary  — 各价格带的销量/GMV/商品数占比
2. shop_concentration  — 店铺集中度（CR5/CR10/HHI）
3. keyword_heat        — 关键词热度榜（销量加权）
4. hot_item_score      — 单 SKU 爆款评分：综合销量、价格带成长性、新品溢价
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .cleaners import attach_price_band, keyword_frequency


# ---------------------------------------------------------------------------
# 1) 价格带分布
# ---------------------------------------------------------------------------

def price_band_summary(df: pd.DataFrame) -> pd.DataFrame:
    """各价格带的商品数、总销量、平均价、GMV 估算。"""
    if df.empty:
        return pd.DataFrame()

    df = attach_price_band(df)
    df["gmv_est"] = df["price"].fillna(0) * df["sold"].fillna(0)

    agg = (
        df.groupby("price_band", dropna=False)
        .agg(
            sku_count=("title", "count"),
            sold_total=("sold", "sum"),
            avg_price=("price", "mean"),
            gmv_est=("gmv_est", "sum"),
        )
        .reset_index()
    )
    total_gmv = agg["gmv_est"].sum() or 1
    total_sold = agg["sold_total"].sum() or 1
    agg["gmv_share_%"] = (agg["gmv_est"] / total_gmv * 100).round(2)
    agg["sold_share_%"] = (agg["sold_total"] / total_sold * 100).round(2)
    agg = agg.sort_values("gmv_est", ascending=False).reset_index(drop=True)
    return agg


# ---------------------------------------------------------------------------
# 2) 店铺集中度
# ---------------------------------------------------------------------------

def shop_concentration(df: pd.DataFrame) -> dict:
    """店铺维度集中度指标。

    Returns
    -------
    dict
        - cr5, cr10        : Top5/Top10 店铺销量占比
        - hhi              : 赫芬达尔指数（0-10000，越大越垄断）
        - top_shops        : 销量 Top 10 店铺明细 DataFrame
    """
    if df.empty or "shop" not in df.columns:
        return {"cr5": 0, "cr10": 0, "hhi": 0, "top_shops": pd.DataFrame()}

    shop_df = (
        df[df["shop"].notna() & (df["shop"].astype(str).str.len() > 0)]
        .groupby("shop")
        .agg(sold=("sold", "sum"), sku=("title", "count"))
        .reset_index()
        .sort_values("sold", ascending=False)
    )

    total = shop_df["sold"].sum() or 1
    shop_df["share_%"] = (shop_df["sold"] / total * 100).round(2)

    cr5 = shop_df.head(5)["share_%"].sum()
    cr10 = shop_df.head(10)["share_%"].sum()
    hhi = float((shop_df["share_%"] ** 2).sum())

    return {
        "cr5": round(cr5, 2),
        "cr10": round(cr10, 2),
        "hhi": round(hhi, 2),
        "top_shops": shop_df.head(10).reset_index(drop=True),
    }


# ---------------------------------------------------------------------------
# 3) 关键词热度
# ---------------------------------------------------------------------------

def keyword_heat(df: pd.DataFrame, top_n: int = 30) -> pd.DataFrame:
    """销量加权的关键词热度榜。"""
    if df.empty:
        return pd.DataFrame()
    kw = keyword_frequency(df, "title", "sold")
    return kw.head(top_n)


# ---------------------------------------------------------------------------
# 4) 爆款打分
# ---------------------------------------------------------------------------

def hot_item_score(df: pd.DataFrame) -> pd.DataFrame:
    """对每个 SKU 做爆款评分（0-100）。

    评分维度（可自由调整权重）：
    - sold_z          : 销量在样本中的 z-score（占 50%）
    - price_band_bonus: 落在主力价格带（30-200 元）+ 10 分
    - new_bonus       : 销量 < 100 但增速极高 → 暗藏潜力（这里简化为单期数据下无法判断，给 0）
    - shop_strength   : 来自高销量店铺 + 5 分
    """
    if df.empty:
        return pd.DataFrame()

    df = attach_price_band(df.copy())

    # 销量 z-score (log 平滑后归一化)
    sold_log = np.log1p(df["sold"].fillna(0))
    if sold_log.std() > 0:
        df["sold_z"] = (sold_log - sold_log.mean()) / sold_log.std()
    else:
        df["sold_z"] = 0.0

    # 主力价格带 bonus
    main_bands = {"30-60 大众款", "60-100 主力款", "100-200 品质款"}
    df["price_bonus"] = df["price_band"].apply(lambda b: 10 if b in main_bands else 0)

    # 店铺强度：店铺累计销量进 Top 20% 加分
    if "shop" in df.columns:
        shop_sold = df.groupby("shop")["sold"].sum()
        cutoff = shop_sold.quantile(0.8) if len(shop_sold) > 5 else float("inf")
        strong_shops = set(shop_sold[shop_sold >= cutoff].index)
        df["shop_bonus"] = df["shop"].apply(lambda s: 5 if s in strong_shops else 0)
    else:
        df["shop_bonus"] = 0

    # 归一化销量分到 [0, 50]
    z_min, z_max = df["sold_z"].min(), df["sold_z"].max()
    if z_max - z_min > 0:
        df["sold_score"] = ((df["sold_z"] - z_min) / (z_max - z_min) * 50).round(2)
    else:
        df["sold_score"] = 25.0

    df["hot_score"] = (df["sold_score"] + df["price_bonus"] + df["shop_bonus"]).clip(0, 100).round(2)

    out_cols = [
        "rank", "title", "price", "sold", "price_band", "shop",
        "sold_score", "price_bonus", "shop_bonus", "hot_score", "url",
    ]
    out_cols = [c for c in out_cols if c in df.columns]
    return df[out_cols].sort_values("hot_score", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# 5) 概览指标（用于 Dashboard 顶部 KPI 卡）
# ---------------------------------------------------------------------------

def overview_kpis(df: pd.DataFrame) -> dict:
    if df.empty:
        return {
            "sku_count": 0, "total_sold": 0, "total_gmv_est": 0,
            "avg_price": 0, "shop_count": 0, "date_range": "—",
        }
    df = df.copy()
    df["gmv_est"] = df["price"].fillna(0) * df["sold"].fillna(0)
    dates = pd.to_datetime(df["date"], errors="coerce").dropna()
    date_range = (
        f"{dates.min().date()} ~ {dates.max().date()}" if len(dates) else "—"
    )
    return {
        "sku_count": int(len(df)),
        "total_sold": int(df["sold"].sum()),
        "total_gmv_est": float(df["gmv_est"].sum()),
        "avg_price": float(df["price"].mean()) if df["price"].notna().any() else 0.0,
        "shop_count": int(df["shop"].nunique()) if "shop" in df.columns else 0,
        "date_range": date_range,
    }
