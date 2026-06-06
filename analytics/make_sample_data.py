"""生成女装球衣类目的模拟示例数据。

用途：
- 在你还没爬到真实数据前，先让 dashboard 有内容可看
- 数据特征贴合女装球衣类目实际：价格带、关键词、店铺名分布都参考真实样本

运行：
    python make_sample_data.py

输出：
    data/samples/taobao_top_女装球衣.csv
    data/samples/taobao_top_棒球服女.csv
    data/samples/manual_history_30d.xlsx   ← 30 天历史销量（用于趋势预测）
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

OUT_DIR = Path(__file__).parent / "data" / "samples"
OUT_DIR.mkdir(parents=True, exist_ok=True)

random.seed(42)


# ---------------------------------------------------------------------------
# 真实感样本组件
# ---------------------------------------------------------------------------

STYLE_WORDS = [
    "美式复古", "ins风", "宽松", "辣妹", "千禧", "Y2K", "学院", "甜酷",
    "嘻哈", "街头", "潮牌", "高街", "vintage", "oversize",
]
CATEGORY_WORDS = [
    "棒球服", "篮球背心", "球衣", "短袖球衣", "运动卫衣", "球迷服",
    "无袖球衣", "T恤", "棒球外套",
]
DETAIL_WORDS = [
    "字母印花", "数字刺绣", "拼接", "v领", "圆领", "短款", "长款", "条纹",
    "格纹", "撞色",
]
SHOPS = [
    "南极人女装旗舰店", "茵曼旗舰店", "雪中飞女装专营店", "ONLY官方旗舰店",
    "太平鸟女装旗舰店", "韩都衣舍旗舰店", "拉夏贝尔旗舰店",
    "美式复古工厂店", "Y2K潮流女装店", "辣妹穿搭研究所", "潮牌集合店",
    "学院风女装店", "球迷服饰旗舰店", "运动潮流店",
]
LOCATIONS = ["广州", "杭州", "上海", "深圳", "苏州", "北京", "成都", "佛山"]


def make_market_csv(keyword: str, n: int = 50, today: date | None = None) -> Path:
    today = today or date.today()
    rows = []
    for i in range(n):
        style = random.choice(STYLE_WORDS)
        cat = random.choice(CATEGORY_WORDS)
        detail = random.choice(DETAIL_WORDS)
        title = f"{style}{cat}女夏季{detail}新款{random.choice(['宽松', '修身', '中长款'])}"
        # 价格按品类合理分布
        price = round(random.choices(
            [random.uniform(19, 39), random.uniform(39, 89), random.uniform(89, 199), random.uniform(199, 499)],
            weights=[0.2, 0.5, 0.25, 0.05],
        )[0], 1)
        # 销量按 Zipf 长尾分布
        sold_num = int(max(50, 20000 / (i + 1) ** 0.85 * random.uniform(0.6, 1.4)))
        if sold_num >= 10000:
            sold_str = f"{sold_num / 10000:.1f}万+"
        else:
            sold_str = f"{sold_num // 100 * 100}+"

        rows.append({
            "rank": i + 1,
            "title": title,
            "price": price,
            "sold": sold_str,
            "shop": random.choice(SHOPS),
            "location": random.choice(LOCATIONS),
            "url": f"https://item.taobao.com/item.htm?id={random.randint(600000000000, 800000000000)}",
            "image": "",
        })

    df = pd.DataFrame(rows)
    path = OUT_DIR / f"taobao_top_{keyword}.csv"
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"[+] {path.relative_to(Path(__file__).parent)}  ({len(df)} 行)")
    return path


def make_history_excel(days: int = 60) -> Path:
    """造一份近 days 天每日销量数据，用来给预测模块演示。

    模拟特征：
    - 整体上升趋势（季度内品类成长）
    - 周末销量略高
    - 含一次"小红书种草引爆"的脉冲（在 -20 天左右）
    """
    today = date.today()
    rows = []
    base = 800
    for i in range(days):
        d = today - timedelta(days=days - 1 - i)
        weekday_bonus = 1.15 if d.weekday() >= 5 else 1.0
        trend = 1 + i * 0.015  # 每天 +1.5%
        spike = 1.6 if days - 1 - i in {18, 19, 20} else 1.0
        noise = random.uniform(0.85, 1.15)
        sold = int(base * weekday_bonus * trend * spike * noise)

        rows.append({
            "date": d.isoformat(),
            "sold": sold,
            "title": "类目日总销量",
            "price": 89.0,
            "category": "女装球衣",
            "source": "manual",
        })

    df = pd.DataFrame(rows)
    path = OUT_DIR / "manual_history_60d.xlsx"
    df.to_excel(path, index=False)
    print(f"[+] {path.relative_to(Path(__file__).parent)}  ({len(df)} 行)")
    return path


def main():
    print(f"[i] 输出目录: {OUT_DIR}")
    make_market_csv("女装球衣", n=60)
    make_market_csv("棒球服女", n=50)
    make_market_csv("篮球背心女", n=40)
    make_history_excel(days=60)
    print("\n[OK] 示例数据已生成。下一步运行 dashboard:")
    print("    streamlit run dashboard.py")


if __name__ == "__main__":
    main()
