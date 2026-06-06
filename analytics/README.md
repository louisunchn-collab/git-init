# 选品爆款分析看板

> 配套 `../taobao_jersey_crawler.py` 使用，把抓到的数据转成可视化的爆款洞察与销量预测。

## 一、3 分钟跑起来

```powershell
cd H:\cursor-class\git-init\analytics

# 1. 装依赖（只做一次）
pip install -r requirements.txt

# 2. 生成示例数据（女装球衣类目模拟样本，让你立即能看到效果）
python make_sample_data.py

# 3. 启动看板
streamlit run dashboard.py
```

浏览器会自动打开 `http://localhost:8501`，你会看到 5 个 Tab 的看板。

## 二、目录结构

```text
analytics/
├── data/
│   ├── raw/                    # ← 把真实爬虫产物放这里
│   ├── samples/                # ← 示例数据 (make_sample_data.py 生成)
│   └── processed/              # 清洗后中间文件 (预留)
├── src/
│   ├── loaders.py              # 数据加载：CSV / 生意参谋 JSON / 手工 Excel
│   ├── cleaners.py             # 销量字符串、价格、标题切词
│   ├── analyzers.py            # 爆款评分、价格带、店铺集中度、关键词热度
│   └── forecaster.py           # 销量预测：移动平均 / Prophet
├── reports/                    # 导出报告（预留）
├── dashboard.py                # Streamlit 看板入口
├── make_sample_data.py         # 生成示例数据
├── requirements.txt
└── README.md
```

## 三、把真实数据接进来

### 1) 来自 `taobao_jersey_crawler.py` 市场模式

爬完后会在上级目录生成 `taobao_top_<关键词>.csv` / `.xlsx`，**把它们丢到 `data/raw/`**：

```powershell
# 在上级目录抓数据
cd H:\cursor-class\git-init
python taobao_jersey_crawler.py --mode market --keyword "棒球服女" --top 50 --pages 2

# 移动到 analytics 数据目录
move taobao_top_*.csv analytics\data\raw\
move taobao_top_*.xlsx analytics\data\raw\
```

侧边栏切到 **"真实数据 (data/raw)"** 即可。

### 2) 来自生意参谋（精确销量，推荐）

```powershell
python taobao_jersey_crawler.py --mode sycm
# 在浏览器里手动浏览：市场 → 商品店铺榜 / 搜索词查询 / 人群画像
# 抓完后整个 sycm_snapshots/ 移过来：
move sycm_snapshots analytics\data\raw\
```

`loaders.py` 会自动遍历 `sycm_snapshots/<timestamp>/*.json`，提取商品榜数据。

### 3) 手工整理的销售数据

任意 Excel/CSV 放到 `data/raw/`，列名能匹配上以下任一组即可：

| 必备列 | 可选列 |
|--------|--------|
| `title`, `sold` (或 `sold_raw`) | `price`, `shop`, `location`, `url`, `date`, `category`, `source` |

文件名以 `manual_` 开头会被自动识别。

## 四、看板说明

### 📊 概览
- 各类目销量对比（颜色=均价）
- 店铺集中度 CR5 / CR10 / HHI（看市场是否被头部垄断）
- 类目趋势信号：累积多日数据后会算出**环比增长率**（爆款前兆）

### 🔥 爆款榜
- 综合评分 = `销量 z-score (50) + 主力价格带 (10) + 强势店铺 (5)`
- 可调 Top N，可直接导出 CSV 用于选品会议

### 💰 价格带
- GMV 与销量在各价格带的分布
- 价格 × 销量散点图：**重点看「价格不高但销量高」的甜点区**（高性价比爆款机会）

### 🔑 关键词
- 标题切词 + 销量加权
- 关注 **`count` 不高但 `sold_weighted` 高的关键词** → 少数 SKU 撑起大销量，潜在蓝海方向

### 📈 销量预测
- 默认：移动平均 + 线性回归外推（零依赖，秒级出图）
- 进阶：`pip install prophet` 后自动切换到 Prophet，能学周/季节性
- 输出未来 N 天日销量曲线 + 置信区间 + 总销量预估

## 五、爆款预测的工作流建议

| 频次 | 动作 | 目的 |
|------|------|------|
| 每周 1 次 | 跑 `--mode market` 抓 3-5 个核心关键词 Top 50 | 看竞品爆款变化 |
| 每周 1-2 次 | 跑 `--mode sycm` 抓商品店铺榜 + 搜索词查询 | 拿到精确销量 + 关键词热度 |
| 每天 1 次 | 自己店铺导出订单/流量 Excel 放 `data/raw/` | 喂给预测模型 |
| 季度初 | 在「关键词」+「爆款榜」Tab 圈出方向，开品 | 输出下季度选品清单 |

数据攒到 **30 天以上**，预测才会真正有参考价值；攒到 **90 天 + 同期对比**，开始能识别季节性。

## 六、常见问题

**Q: 跑 `streamlit run dashboard.py` 报 "ModuleNotFoundError: No module named 'src'"？**  
A: 一定要 `cd analytics` 后再启动，否则相对导入找不到。

**Q: 关键词切词不准？**  
A: 编辑 `src/cleaners.py` 的 `_STOPWORDS`，把你类目里没区分度的词加进去（如"包邮"/"夏季"）。

**Q: 价格带分桶不符合我的类目？**  
A: 改 `src/cleaners.py` 里的 `PRICE_BANDS` 常量，按你品类的心理价位调整。

**Q: 想要 Prophet 预测？**  
A: `pip install prophet`（首次装会编译 cmdstan，可能要 5 分钟），完成后预测方法选 `prophet`。

**Q: 想做"自动每周生成报告并发钉钉"？**  
A: 可以扩展 `reports/` 目录 + 写一个 `weekly_report.py`，用 Windows 任务计划 / cron 调度。需要时再加。
