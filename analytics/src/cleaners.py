"""字段清洗工具。

把"5000+"/"1.2万"/"￥199.00"这种字符串规整成数值，
再做价格分桶、标题切词等下游分析必备的预处理。
"""

from __future__ import annotations

import re
from typing import Iterable

import pandas as pd

# 价格带（元）—— 针对女装球衣类目的常见区间。
# 调整时尽量保留 0/30/60/100/200/500 这几个心理价位边界。
PRICE_BANDS = [
    (0, 30, "≤30 极致引流款"),
    (30, 60, "30-60 大众款"),
    (60, 100, "60-100 主力款"),
    (100, 200, "100-200 品质款"),
    (200, 500, "200-500 设计师款"),
    (500, 9999, "500+ 高端款"),
]


# ---------------------------------------------------------------------------
# 销量字符串 -> 数值
# ---------------------------------------------------------------------------

_NUM_RE = re.compile(r"([\d.]+)")


def parse_sold(s) -> float:
    """`"5000+"` / `"1.2万"` / `"已售 3000"` / `200` 一律转 float。

    区间值（带 `+`）按下界返回，保守估计。
    """
    if s is None:
        return 0.0
    if isinstance(s, (int, float)):
        return float(s)
    text = str(s).strip()
    if not text:
        return 0.0

    has_wan = "万" in text or "w" in text.lower()
    m = _NUM_RE.search(text)
    if not m:
        return 0.0
    try:
        value = float(m.group(1))
    except ValueError:
        return 0.0

    if has_wan:
        value *= 10000
    return value


def parse_price(s) -> float:
    """`"¥199.00"` / `"199-299"` / `199` -> float。区间取下界。"""
    if s is None:
        return 0.0
    if isinstance(s, (int, float)):
        return float(s)
    text = str(s).strip().replace("¥", "").replace("￥", "").replace(",", "")
    if not text:
        return 0.0
    m = _NUM_RE.search(text)
    if not m:
        return 0.0
    try:
        return float(m.group(1))
    except ValueError:
        return 0.0


# ---------------------------------------------------------------------------
# 价格带分桶
# ---------------------------------------------------------------------------

def assign_price_band(price: float) -> str:
    for lo, hi, label in PRICE_BANDS:
        if lo <= price < hi:
            return label
    return "未知"


def attach_price_band(df: pd.DataFrame, col: str = "price") -> pd.DataFrame:
    df = df.copy()
    df["price_band"] = df[col].apply(assign_price_band)
    return df


# ---------------------------------------------------------------------------
# 标题切词（中文）
# ---------------------------------------------------------------------------

# 这些词在女装球衣类目里频繁出现但缺乏区分度，作为停用词剔除。
_STOPWORDS = {
    "女装", "女士", "女款", "新款", "夏季", "夏天", "春秋", "冬季", "韩版",
    "时尚", "百搭", "宽松", "ins", "美式", "复古", "潮流",
    "包邮", "正品", "官方", "旗舰", "店", "套装", "短袖", "长袖",
    "件", "套", "款", "的", "和", "与", "及",
}


def tokenize_titles(titles: Iterable[str]) -> list[list[str]]:
    """对一批标题做中文切词，去停用词。"""
    try:
        import jieba
    except ImportError:
        # 退化方案：按非中英文字符分割
        return [
            [w for w in re.split(r"[^\w\u4e00-\u9fa5]+", t or "") if w and w not in _STOPWORDS]
            for t in titles
        ]

    out: list[list[str]] = []
    for t in titles:
        tokens = [
            w.strip()
            for w in jieba.cut(t or "")
            if w.strip() and w.strip() not in _STOPWORDS and len(w.strip()) > 1
        ]
        out.append(tokens)
    return out


def keyword_frequency(df: pd.DataFrame, title_col: str = "title", weight_col: str | None = "sold") -> pd.DataFrame:
    """统计标题关键词频次。可选用销量加权。

    Returns
    -------
    DataFrame[columns=keyword, count, sold_weighted]
    """
    titles = df[title_col].fillna("").tolist()
    weights = df[weight_col].fillna(0).tolist() if weight_col and weight_col in df.columns else [1.0] * len(titles)

    token_lists = tokenize_titles(titles)
    counter: dict[str, dict] = {}
    for tokens, w in zip(token_lists, weights):
        for kw in set(tokens):
            stats = counter.setdefault(kw, {"count": 0, "sold_weighted": 0.0})
            stats["count"] += 1
            stats["sold_weighted"] += float(w or 0)

    rows = [{"keyword": k, **v} for k, v in counter.items()]
    return pd.DataFrame(rows).sort_values("sold_weighted", ascending=False).reset_index(drop=True)
