"""电商选品数据分析看板 — Streamlit 入口。

启动：
    cd analytics
    streamlit run dashboard.py

第一次启动时如果 data/ 下没有数据，会自动加载 data/samples/ 里的示例数据，
让你立刻能看到完整的看板效果。
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from src import analyzers, forecaster, loaders
from src.cleaners import attach_price_band

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
SAMPLE_DIR = DATA_DIR / "samples"


# ---------------------------------------------------------------------------
# 页面基础配置
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="选品爆款分析看板",
    page_icon="🛍️",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data(show_spinner=False)
def load_data(use_samples: bool) -> pd.DataFrame:
    target = SAMPLE_DIR if use_samples else DATA_DIR
    return loaders.load_all(target)


# ---------------------------------------------------------------------------
# 侧边栏：数据源选择 + 类目筛选
# ---------------------------------------------------------------------------

st.sidebar.title("🛍️ 数据源")
data_mode = st.sidebar.radio(
    "选择数据来源",
    ["真实数据 (data/raw)", "示例数据 (data/samples)"],
    index=1,
    help="把爬虫产物放到 data/raw/ 下后切到第一项",
)
use_samples = data_mode.startswith("示例")

df = load_data(use_samples=use_samples)

if df.empty:
    st.warning(
        "⚠️ 暂无数据。请先运行 `python make_sample_data.py` 生成示例数据，"
        "或者把爬虫输出放到 `data/raw/` 下。"
    )
    st.stop()

# 类目筛选
all_categories = sorted([c for c in df["category"].dropna().unique() if str(c).strip()])
selected = st.sidebar.multiselect(
    "类目 / 关键词", all_categories, default=all_categories,
    help="对应爬虫的 keyword，例如「女装球衣」「棒球服女」",
)
if selected:
    df = df[df["category"].isin(selected)]

# 数据来源筛选
sources = sorted(df["source"].dropna().unique().tolist())
if len(sources) > 1:
    src_sel = st.sidebar.multiselect("数据来源", sources, default=sources)
    df = df[df["source"].isin(src_sel)]

st.sidebar.markdown("---")
st.sidebar.markdown(
    "📦 **数据列表**\n\n"
    f"- 总 SKU: **{len(df)}**\n"
    f"- 类目: **{df['category'].nunique()}**\n"
    f"- 店铺: **{df['shop'].nunique() if 'shop' in df.columns else 0}**\n"
    f"- 时间: `{df['date'].min()} ~ {df['date'].max()}`"
)


# ---------------------------------------------------------------------------
# 顶部 KPI 卡片
# ---------------------------------------------------------------------------

st.title("🛍️ 选品爆款分析看板")
st.caption("基于爬虫输出 + 生意参谋 XHR 数据，做爆款评分 + 价格带分析 + 销量预测")

kpis = analyzers.overview_kpis(df)
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("商品总数", f"{kpis['sku_count']:,}")
c2.metric("销量合计", f"{kpis['total_sold']:,}")
c3.metric("GMV 估算 (¥)", f"{kpis['total_gmv_est']:,.0f}")
c4.metric("平均价 (¥)", f"{kpis['avg_price']:,.1f}")
c5.metric("店铺数", f"{kpis['shop_count']:,}")


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab_overview, tab_top, tab_price, tab_keyword, tab_forecast = st.tabs(
    ["📊 概览", "🔥 爆款榜", "💰 价格带", "🔑 关键词", "📈 销量预测"]
)


# --------- Tab 1: 概览 ---------
with tab_overview:
    col_left, col_right = st.columns([1.3, 1])

    with col_left:
        st.subheader("各类目销量对比")
        cat_summary = (
            df.groupby("category")
            .agg(sku=("title", "count"), sold=("sold", "sum"), avg_price=("price", "mean"))
            .reset_index()
            .sort_values("sold", ascending=False)
        )
        fig = px.bar(
            cat_summary, x="category", y="sold", color="avg_price",
            color_continuous_scale="Tealrose",
            labels={"category": "类目", "sold": "总销量", "avg_price": "均价"},
            title="类目销量与均价",
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_right:
        st.subheader("店铺集中度")
        sc = analyzers.shop_concentration(df)
        st.metric("CR5  Top5 店铺销量占比", f"{sc['cr5']:.1f}%")
        st.metric("CR10 Top10 店铺销量占比", f"{sc['cr10']:.1f}%")
        st.metric("HHI 赫芬达尔指数", f"{sc['hhi']:.0f}",
                  help="< 1500 充分竞争 / 1500-2500 中度集中 / > 2500 高度集中")
        st.markdown("**Top 10 店铺**")
        st.dataframe(sc["top_shops"], use_container_width=True, hide_index=True)

    st.subheader("类目趋势信号（环比）")
    trend = forecaster.category_trend_signal(df)
    if trend.empty:
        st.info("当前数据只有单期/单天，无法计算环比。多次抓取累积数据后会显示。")
    else:
        st.dataframe(trend, use_container_width=True, hide_index=True)


# --------- Tab 2: 爆款榜 ---------
with tab_top:
    st.subheader("🔥 爆款 SKU 评分榜")
    st.caption("评分维度：销量 z-score（50）+ 主力价格带（10）+ 强势店铺（5），综合到 0-100 分。")

    score_df = analyzers.hot_item_score(df)
    top_n = st.slider("显示前 N 名", 10, min(100, len(score_df)), min(30, len(score_df)))

    show = score_df.head(top_n)
    st.dataframe(
        show,
        use_container_width=True,
        hide_index=True,
        column_config={
            "hot_score": st.column_config.ProgressColumn(
                "爆款评分", format="%.1f", min_value=0, max_value=100
            ),
            "price": st.column_config.NumberColumn("价格", format="¥%.1f"),
            "sold": st.column_config.NumberColumn("销量", format="%d"),
            "url": st.column_config.LinkColumn("链接", display_text="跳转"),
        },
    )

    st.download_button(
        "⬇️ 导出当前榜单为 CSV",
        data=show.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
        file_name="hot_items.csv",
        mime="text/csv",
    )


# --------- Tab 3: 价格带 ---------
with tab_price:
    st.subheader("💰 价格带分布")
    pb = analyzers.price_band_summary(df)
    if pb.empty:
        st.info("暂无价格数据。")
    else:
        c1, c2 = st.columns(2)
        with c1:
            fig = px.bar(
                pb, x="price_band", y="gmv_share_%",
                title="GMV 占比 (%)",
                labels={"price_band": "价格带", "gmv_share_%": "GMV 占比"},
                color="gmv_share_%", color_continuous_scale="Sunset",
            )
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            fig2 = px.bar(
                pb, x="price_band", y="sold_total",
                title="销量分布",
                labels={"price_band": "价格带", "sold_total": "销量合计"},
                color="sold_total", color_continuous_scale="Viridis",
            )
            st.plotly_chart(fig2, use_container_width=True)

        st.dataframe(pb, use_container_width=True, hide_index=True)

    st.subheader("价格 × 销量散点（点大小=GMV）")
    sct_df = attach_price_band(df).copy()
    sct_df["gmv_est"] = sct_df["price"].fillna(0) * sct_df["sold"].fillna(0)
    sct = px.scatter(
        sct_df, x="price", y="sold", color="price_band", size="gmv_est",
        hover_data=["title", "shop"], opacity=0.7,
        labels={"price": "价格 (¥)", "sold": "销量"},
        title="找出『价格不高但销量高』的甜点区",
    )
    st.plotly_chart(sct, use_container_width=True)


# --------- Tab 4: 关键词 ---------
with tab_keyword:
    st.subheader("🔑 关键词热度榜（销量加权）")
    top_kw = st.slider("Top N 关键词", 10, 60, 30, key="kw_top")
    kw_df = analyzers.keyword_heat(df, top_n=top_kw)
    if kw_df.empty:
        st.info("无关键词数据。")
    else:
        c1, c2 = st.columns([1, 1.2])
        with c1:
            st.dataframe(kw_df, use_container_width=True, hide_index=True)
        with c2:
            fig = px.bar(
                kw_df.head(20).iloc[::-1],
                x="sold_weighted", y="keyword", orientation="h",
                title="Top 20 关键词销量加权",
                labels={"sold_weighted": "销量加权热度", "keyword": "关键词"},
            )
            st.plotly_chart(fig, use_container_width=True)

        st.markdown(
            "**💡 选品启示**：销量加权排名靠前但 `count` 不高的关键词 = "
            "「少数商品贡献大销量」→ 可能存在还未被充分挖掘的细分爆款方向。"
        )


# --------- Tab 5: 预测 ---------
with tab_forecast:
    st.subheader("📈 类目销量预测")

    horizon = st.slider("预测未来多少天", 7, 90, 30)
    method_label = st.radio(
        "预测方法",
        ["auto (自动)", "ma (移动平均+线性外推)", "prophet (需先 pip install prophet)"],
        horizontal=True,
    )
    method = method_label.split()[0]

    fc = forecaster.forecast_sold(df, horizon_days=horizon, method=method)  # type: ignore
    if fc.empty:
        st.info("当前数据中能解析为日期的数据点 < 3 条，无法预测。先把 `manual_history_*.xlsx` 放入 `data/`。")
    else:
        fc_plot = fc.copy()
        fc_plot["date"] = pd.to_datetime(fc_plot["date"])
        fig = px.line(
            fc_plot, x="date", y=["sold", "forecast"],
            labels={"value": "销量", "date": "日期", "variable": "类型"},
            title=f"未来 {horizon} 天销量预测",
        )
        # 置信区间填色
        if fc_plot["yhat_lower"].notna().any():
            fig.add_scatter(
                x=fc_plot["date"], y=fc_plot["yhat_upper"],
                mode="lines", line=dict(width=0), showlegend=False, name="upper",
            )
            fig.add_scatter(
                x=fc_plot["date"], y=fc_plot["yhat_lower"],
                mode="lines", line=dict(width=0),
                fill="tonexty", fillcolor="rgba(120,200,255,0.2)",
                showlegend=True, name="80% 置信区间",
            )
        st.plotly_chart(fig, use_container_width=True)

        # 未来 N 天汇总预估
        future_only = fc_plot[fc_plot["sold"].isna()].copy()
        if not future_only.empty:
            total_pred = future_only["forecast"].sum()
            avg_daily = future_only["forecast"].mean()
            st.success(
                f"📊 预计未来 **{horizon}** 天总销量约 **{total_pred:,.0f}** 件 "
                f"(日均 **{avg_daily:,.0f}** 件)"
            )

        with st.expander("查看预测明细"):
            st.dataframe(fc, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# 页脚
# ---------------------------------------------------------------------------

st.markdown("---")
st.caption(
    "数据通道：`taobao_jersey_crawler.py` → CSV / 生意参谋 XHR JSON → "
    "`analytics/` 自动加载分析。"
)
