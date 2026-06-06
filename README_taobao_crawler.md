# 淘宝女装球衣销量抓取脚本 — 快速上手

> 本脚本仅用于**自己商家**做选品研究，不建议大规模 / 高频抓取。

## 一、环境准备（只做一次）

打开 PowerShell：

```powershell
# 1. 安装依赖
pip install playwright pandas openpyxl

# 2. 下载 Chromium 内核 (约 150MB)
playwright install chromium
```

## 二、第一次运行

```powershell
cd H:\cursor-class\git-init
python taobao_jersey_crawler.py --keyword "女装球衣" --top 10 --pages 2 --headful
```

执行后会发生：

1. 弹出 Chrome 浏览器窗口，自动打开淘宝
2. **手动扫码登录**（推荐用淘宝 APP 扫码）
3. 登录成功后回到 PowerShell 终端，**按 Enter** 开始抓取
4. 脚本会保存 `taobao_state.json`，下次自动复用登录态

完成后会生成两个文件：

- `taobao_top_女装球衣.csv`
- `taobao_top_女装球衣.xlsx`

## 三、常用命令示例

### 模式 1：淘宝公开搜索（市场调研用，销量为区间值）

```powershell
# 抓取"棒球服女"销量 Top 30，翻 2 页
python taobao_jersey_crawler.py --mode market --keyword "棒球服女" --top 30 --pages 2

# 抓取"球衣女 美式复古"翻 3 页
python taobao_jersey_crawler.py --mode market --keyword "球衣女 美式复古" --top 50 --pages 3

# 后续运行（已登录）可隐藏浏览器窗口
python taobao_jersey_crawler.py --mode market --keyword "篮球背心女" --top 20
```

### 模式 2：生意参谋抓取（商家专用，**精确销量**） ⭐

```powershell
python taobao_jersey_crawler.py --mode sycm
```

**这个模式做了什么**：

1. 启动 Chrome 浏览器（如未登录则提示扫码登录千牛账号）
2. 自动打开生意参谋首页
3. **你手动**在浏览器里导航到任意页面（例如"市场 → 商品店铺榜 → 女装球衣"）
4. 脚本在后台**自动拦截**所有 `sycm.taobao.com` 返回的 JSON 数据
5. 你可以连续打开多个页面，每个页面的数据都会自动落盘
6. 全部抓完后，回终端按 Enter 结束

**输出位置**：

```
H:\cursor-class\git-init\sycm_snapshots\20260512_165000\
├── 1747125632123_sycm.taobao.com_mq_industry_rank.json   ← 商品店铺榜
├── 1747125645211_sycm.taobao.com_mq_search_keyword.json  ← 搜索词查询
├── 1747125661887_sycm.taobao.com_flow_overview.json      ← 流量概览
└── _index.json                                            ← 所有文件索引
```

**为什么不直接传 URL 抓**：生意参谋接口经常变（一个季度改一次路径），写死的 URL 三个月就失效。**XHR 拦截法**只要数据是 JSON 返回，就一定能抓到，对页面改版有极强的鲁棒性。

**推荐你打开的页面**（按"女装球衣"选品研究优先级排序）：

| 优先级 | 路径 | 你能拿到什么 |
|--------|------|--------------|
| ★★★ | 市场 → 商品店铺榜 → 选"女装/连衣裙"类目 | **同行精确销量 Top 榜**（你最初问的） |
| ★★★ | 市场 → 搜索词查询 → 搜"球衣" | 关键词热度、点击率、转化率、在线商品数 |
| ★★ | 市场 → 人群画像 → 选"球衣"关键词 | 买家年龄/性别/地域/消费层级 |
| ★★ | 流量 → 我的店铺 → 商品分析 | 你自己店铺的爆款走势 |
| ★ | 市场 → 大盘趋势 | 类目大盘的近 30 天搜索/成交曲线 |

## 四、参数说明

| 参数        | 默认值       | 说明                              |
|-------------|--------------|-----------------------------------|
| `--keyword` | `女装球衣`   | 搜索关键词                        |
| `--top`     | `10`         | 保留前 N 名                       |
| `--pages`   | `1`          | 最多翻几页（每页约 44 件）        |
| `--output`  | `taobao_top` | 输出文件前缀                      |
| `--headful` | 关闭         | 显示浏览器窗口（首次登录必须开） |

## 五、注意事项

⚠ **风控提示**：
- 单次抓取建议 ≤ 100 条
- 不要短时间内连续运行
- 若出现滑块验证，手动完成即可
- 频繁运行可能导致账号临时限制

⚠ **数据准确性**：
- 淘宝公开页面销量仅显示"已售 100+ / 1000+"等区间值
- 真正精确销量需登录**生意参谋**抓取（脚本已预留登录入口）
- 排序按淘宝官方的 `sort=sale-desc` 综合销量算法

⚠ **法律合规**：
- 抓到的数据**仅供个人使用**
- 不要二次售卖、公开发布或用于竞品攻击
- 阿里用户协议禁止商业级自动化抓取

## 六、常见问题

**Q: 跑起来报错 "executable not found"？**  
A: 没执行 `playwright install chromium`，补一下。

**Q: 一直被风控（滑块/空白页）？**  
A: 加大 `--pages` 之间的间隔，或换用 `--headful` 模式手动协助通过验证。

**Q: 标题/价格抓不准？**  
A: 淘宝前端结构经常变，请打开 `taobao_jersey_crawler.py` 的 `search_and_extract` 函数，调整页面级 JS 中的 CSS 选择器。

**Q: 想抓生意参谋的真实销量？**  
A: 直接用 `--mode sycm`，详见上文"模式 2"章节。

**Q: 抓到的 JSON 怎么解析？**  
A: 每个文件结构大致是：

```json
{
  "url": "https://sycm.taobao.com/mq/industry/rank?...",
  "body": {
    "code": "0",
    "data": {
      "list": [
        { "rank": 1, "itemTitle": "...", "payAmt": 12345.67, "payItmCnt": 200, ... },
        ...
      ]
    }
  }
}
```

最关心的字段一般在 `body.data.list[]`，用 pandas 一行展平：

```python
import json, pandas as pd
data = json.load(open("xxx.json", encoding="utf-8"))
df = pd.DataFrame(data["body"]["data"]["list"])
df.to_excel("top_products.xlsx", index=False)
```

**Q: 抓生意参谋会被封号吗？**  
A: 风险**极低**。脚本只拦截你**正常浏览页面时的接口返回**，行为模式与你手动点击完全一致，没有自动化点击/翻页/批量请求。控制每天 ≤ 几次手动抓取即可。
