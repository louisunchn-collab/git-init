"""数据加载器。

支持三类数据源：
1. taobao_top_*.csv / *.xlsx   — `taobao_jersey_crawler.py` 市场模式输出
2. sycm_snapshots/<ts>/*.json  — 生意参谋 XHR 拦截输出（精确销量）
3. data/raw/*.xlsx / *.csv     — 你自己手动整理的任意销售数据，
                                  列名能匹配上 `STANDARD_COLUMNS` 即可

最终统一返回一个 pandas DataFrame，列名遵循 `STANDARD_COLUMNS`。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import pandas as pd

# 全项目统一字段（中文友好 + 英文键并存）。
# 后续 analyzers / dashboard 都以这套字段为准。
STANDARD_COLUMNS = [
    "rank",        # 排名
    "title",       # 商品标题
    "price",       # 价格（元，float）
    "sold",        # 销量（件，float；区间值取下界）
    "sold_raw",    # 原始销量字符串，例如 "5000+" / "1.2万"
    "shop",        # 店铺名
    "location",    # 发货地
    "url",         # 商品链接
    "image",       # 主图 URL
    "category",    # 类目（可选）
    "date",        # 数据采集日期（YYYY-MM-DD）
    "source",      # 数据来源：market / sycm / manual
]


# ---------------------------------------------------------------------------
# 1) 市场公开抓取 (taobao_jersey_crawler.py --mode market)
# ---------------------------------------------------------------------------

def load_market_csv(path: str | Path) -> pd.DataFrame:
    """加载 `taobao_top_<关键词>.csv` 或 `.xlsx`。"""
    path = Path(path)
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path, encoding="utf-8-sig")
    else:
        df = pd.read_excel(path)

    df = df.rename(columns={"sold": "sold_raw"})
    df["source"] = "market"
    df["date"] = _file_date(path)
    if "category" not in df.columns:
        # 从文件名推 keyword 作为类目
        df["category"] = path.stem.replace("taobao_top_", "").replace("_", " ")
    return _normalize(df)


# ---------------------------------------------------------------------------
# 2) 生意参谋 XHR 拦截输出 (--mode sycm)
# ---------------------------------------------------------------------------

# 生意参谋 JSON 里"商品店铺榜"的常见字段映射。
# 不同接口字段名差异较大，这里覆盖最常见的几种。
_SYCM_FIELD_MAP = {
    "itemTitle":   "title",
    "title":       "title",
    "itemName":    "title",
    "payAmt":      "gmv",
    "payItmCnt":   "sold",
    "ordItmQty":   "sold",
    "payByrCnt":   "buyers",
    "uv":          "uv",
    "price":       "price",
    "avgPrice":    "price",
    "shopName":    "shop",
    "sellerNick":  "shop",
    "itemUrl":     "url",
    "rank":        "rank",
    "rankNum":     "rank",
}


def load_sycm_snapshot(snapshot_dir: str | Path) -> pd.DataFrame:
    """加载某次生意参谋抓取目录下所有 *.json，合并为商品榜 DataFrame。

    Parameters
    ----------
    snapshot_dir : str | Path
        例如 `sycm_snapshots/20260512_165000`。
    """
    snapshot_dir = Path(snapshot_dir)
    rows: list[dict] = []
    for json_file in snapshot_dir.glob("*.json"):
        if json_file.name == "_index.json":
            continue
        try:
            payload = json.loads(json_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        # 数据通常嵌在 body.data.list / body.data.data 中
        for list_node in _walk_lists(payload.get("body", payload)):
            for item in list_node:
                if not isinstance(item, dict):
                    continue
                row = {}
                for k, v in item.items():
                    if k in _SYCM_FIELD_MAP:
                        row[_SYCM_FIELD_MAP[k]] = v
                if "title" in row or "sold" in row:
                    rows.append(row)

    if not rows:
        return pd.DataFrame(columns=STANDARD_COLUMNS)

    df = pd.DataFrame(rows)
    df["source"] = "sycm"
    df["date"] = snapshot_dir.name[:8] if snapshot_dir.name[:8].isdigit() else _file_date(snapshot_dir)
    if "category" not in df.columns:
        df["category"] = snapshot_dir.name
    return _normalize(df)


def _walk_lists(node) -> Iterable[list]:
    """深度遍历嵌套 dict/list，yield 出所有 list 节点。"""
    if isinstance(node, list):
        # 只取 list-of-dict
        if node and isinstance(node[0], dict):
            yield node
        for item in node:
            yield from _walk_lists(item)
    elif isinstance(node, dict):
        for v in node.values():
            yield from _walk_lists(v)


# ---------------------------------------------------------------------------
# 3) 手动整理的销售数据
# ---------------------------------------------------------------------------

def load_manual(path: str | Path) -> pd.DataFrame:
    """加载你自己整理的 Excel/CSV。列名只要能对应上 STANDARD_COLUMNS 即可。"""
    path = Path(path)
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path, encoding="utf-8-sig")
    else:
        df = pd.read_excel(path)
    df["source"] = df.get("source", "manual")
    if "date" not in df.columns:
        df["date"] = _file_date(path)
    return _normalize(df)


# ---------------------------------------------------------------------------
# 4) 一站式：扫描目录里全部受支持的数据
# ---------------------------------------------------------------------------

def load_all(data_dir: str | Path = "data") -> pd.DataFrame:
    """递归扫描 data/ 目录，合并所有受支持的数据源。"""
    data_dir = Path(data_dir)
    frames: list[pd.DataFrame] = []

    for csv in data_dir.rglob("taobao_top_*.csv"):
        frames.append(load_market_csv(csv))
    for xlsx in data_dir.rglob("taobao_top_*.xlsx"):
        frames.append(load_market_csv(xlsx))

    for snap in data_dir.rglob("sycm_snapshots/*/"):
        if snap.is_dir():
            frames.append(load_sycm_snapshot(snap))
    # 也接受任意名字下的 sycm_*.json 单文件
    for json_file in data_dir.rglob("sycm_*.json"):
        frames.append(load_sycm_snapshot(json_file.parent))

    for manual in data_dir.rglob("manual_*.xlsx"):
        frames.append(load_manual(manual))
    for manual in data_dir.rglob("manual_*.csv"):
        frames.append(load_manual(manual))

    if not frames:
        return pd.DataFrame(columns=STANDARD_COLUMNS)

    merged = pd.concat(frames, ignore_index=True, sort=False)
    return _normalize(merged)


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------

def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """补齐缺失列、规整类型、去重。"""
    from .cleaners import parse_sold, parse_price

    for col in STANDARD_COLUMNS:
        if col not in df.columns:
            df[col] = None

    # 销量：优先用已有 sold（数值），否则从 sold_raw 解析
    if df["sold"].isna().all() and not df["sold_raw"].isna().all():
        df["sold"] = df["sold_raw"].apply(parse_sold)
    else:
        df["sold"] = df["sold"].fillna(df["sold_raw"].apply(parse_sold))

    df["price"] = df["price"].apply(parse_price)
    df["sold"] = pd.to_numeric(df["sold"], errors="coerce").fillna(0)

    # 去重：同一天 + 同一标题
    df = df.drop_duplicates(subset=["date", "title"], keep="first")

    return df[STANDARD_COLUMNS + [c for c in df.columns if c not in STANDARD_COLUMNS]]


def _file_date(path: Path) -> str:
    """从文件 mtime 推日期。"""
    import datetime as dt
    ts = path.stat().st_mtime if path.exists() else dt.datetime.now().timestamp()
    return dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
