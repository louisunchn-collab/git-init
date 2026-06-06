"""
淘宝女装球衣 Top N 抓取脚本
============================

用途：在你本地电脑上运行，使用 Playwright 控制 Chrome 浏览器，
让你手动扫码登录一次淘宝/千牛，然后自动抓取指定关键词的
"销量排序" Top N 商品，导出为 CSV 和 Excel。

为什么这个脚本要"本地运行"：
  - 淘宝/天猫的搜索结果页 (s.taobao.com) 必须登录态访问
  - 登录态需要你的扫码 / 账号密码 / 千牛态——这只能在你本机完成
  - 本机 IP + 真实浏览器 UA 才能绕过淘宝风控

================================
环境准备 (只需一次)
================================

1. 安装 Python 3.9+ (https://www.python.org/downloads/)
2. 在本目录打开 PowerShell，运行：

       pip install playwright pandas openpyxl
       playwright install chromium

   (第二条命令会下载约 150MB 的 Chromium 浏览器内核)

================================
使用方法
================================

    python taobao_jersey_crawler.py --keyword "女装球衣" --top 10 --pages 2

参数：
    --keyword   搜索关键词，默认 "女装球衣"
    --top       要抓取的 Top N 商品数，默认 10
    --pages     最多翻几页 (每页约 44 件)，默认 1
    --output    输出文件前缀，默认 taobao_top
    --headful   显示浏览器窗口（首次扫码登录时必须）

第一次运行：
    1. 脚本会打开 Chrome 窗口并访问淘宝
    2. 你手动扫码 / 账号密码登录
    3. 登录成功后回到终端，按回车开始抓取
    4. Cookie 会保存到 ./taobao_state.json，下次自动复用

================================
合规与免责
================================

  ⚠ 本脚本仅用于个人商家做市场研究 / 选品参考。
  ⚠ 阿里巴巴用户协议禁止大规模自动化抓取；建议：
       - 单次抓取条数 ≤ 100
       - 抓取间隔 ≥ 2 秒
       - 不要频繁运行
  ⚠ 使用本脚本由你本人承担风控风险（账号可能被临时限制）。
  ⚠ 抓到的数据不要二次售卖 / 公开传播。

"""

import argparse
import asyncio
import csv
import json
import os
import random
import re
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional

try:
    from playwright.async_api import async_playwright, Page, BrowserContext, Response
except ImportError:
    print("[!] 缺少依赖 playwright。请先执行：")
    print("    pip install playwright pandas openpyxl")
    print("    playwright install chromium")
    sys.exit(1)


# -----------------------------------------------------------------------------
# 数据结构
# -----------------------------------------------------------------------------

@dataclass
class Product:
    rank: int
    title: str
    price: str
    sold: str
    shop: str
    location: str
    url: str
    image: str


# -----------------------------------------------------------------------------
# 核心逻辑
# -----------------------------------------------------------------------------

STATE_FILE = Path(__file__).parent / "taobao_state.json"


async def ensure_login(context: BrowserContext, page: Page) -> None:
    """打开淘宝首页，让用户手动登录。"""
    await page.goto("https://www.taobao.com/", wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)

    # 检查是否已经是登录态
    try:
        # 已登录时页面顶部会显示用户名而不是"亲，请登录"
        login_text = await page.locator("text=亲，请登录").count()
        if login_text == 0:
            print("[+] 已检测到登录态，跳过登录步骤。")
            return
    except Exception:
        pass

    print("\n" + "=" * 60)
    print("请在打开的 Chrome 窗口中完成淘宝登录（扫码或账密均可）。")
    print("登录成功后回到这里，按 Enter 继续抓取...")
    print("=" * 60)
    input()

    # 保存登录态
    await context.storage_state(path=str(STATE_FILE))
    print(f"[+] 登录态已保存到 {STATE_FILE}")


async def search_and_extract(
    page: Page, keyword: str, page_num: int = 1
) -> List[Product]:
    """搜索关键词并按销量排序抓取一页商品。"""
    # 销量排序：sort=sale-desc
    # 分页：s=(page_num-1)*44
    s_offset = (page_num - 1) * 44
    url = (
        f"https://s.taobao.com/search?q={keyword}"
        f"&sort=sale-desc&s={s_offset}"
    )
    print(f"[>] 抓取第 {page_num} 页：{url}")
    await page.goto(url, wait_until="domcontentloaded")

    # 模拟人类滚动行为以触发懒加载 + 降低风控分
    for _ in range(6):
        await page.mouse.wheel(0, random.randint(300, 600))
        await page.wait_for_timeout(random.randint(300, 700))

    # 等待商品列表出现 (淘宝结构经常变，这里尝试多个选择器)
    selectors = [
        'div[data-category="auctions"] a[href*="item.taobao"]',
        'a.search-card-item',
        'div.J_MouserOnverReq',
        'a[href*="item.taobao.com"]',
    ]

    items_handle = None
    for sel in selectors:
        try:
            await page.wait_for_selector(sel, timeout=4000)
            items_handle = sel
            break
        except Exception:
            continue

    if not items_handle:
        print("[!] 没找到商品节点。可能：(1) 触发风控  (2) 页面结构变化")
        print("    请手动滚动页面看是否有滑块验证，完成后在终端按 Enter 重试。")
        input()
        return []

    # 用页面级 JS 提取所有商品卡片
    products = await page.evaluate(
        """
        () => {
            const cards = document.querySelectorAll('a[href*="item.taobao.com"], a.search-card-item');
            const seen = new Set();
            const out = [];
            cards.forEach(card => {
                const href = card.href || '';
                const m = href.match(/id=(\\d+)/) || href.match(/item\\.taobao\\.com\\/item\\.htm\\?[^"]*id=(\\d+)/);
                const itemId = m ? m[1] : href;
                if (seen.has(itemId)) return;
                seen.add(itemId);

                const root = card.closest('div') || card;
                const text = root.innerText || '';

                // 提取价格
                const priceM = text.match(/¥\\s*([\\d.]+)|￥\\s*([\\d.]+)/);
                const price = priceM ? (priceM[1] || priceM[2]) : '';

                // 提取销量
                const soldM = text.match(/(月销|已售)\\s*([\\d.]+[万+\\d]*)/);
                const sold = soldM ? soldM[2] : '';

                // 提取标题：优先 img alt
                const img = root.querySelector('img');
                const title = (img && img.alt) ? img.alt.trim() :
                              (text.split('\\n')[0] || '').slice(0, 80);

                // 店铺名 (启发式：包含"店"或"旗舰店"的短文本)
                const shopMatch = text.match(/([\\w\\u4e00-\\u9fa5]{2,20}(?:旗舰店|专营店|官方店|店))/);
                const shop = shopMatch ? shopMatch[1] : '';

                // 发货地
                const locMatch = text.match(/([\\u4e00-\\u9fa5]{2,4}\\s*[\\u4e00-\\u9fa5]{0,4})/);
                const location = locMatch ? locMatch[1] : '';

                const imgUrl = img ? (img.src || img.dataset.src || '') : '';

                out.push({ title, price, sold, shop, location, url: href, image: imgUrl });
            });
            return out;
        }
        """
    )

    print(f"[+] 第 {page_num} 页提取到 {len(products)} 件商品。")
    return [
        Product(rank=0, **p)
        for p in products
        if p.get("title") and len(p.get("title", "")) > 4
    ]


def parse_sold(s: str) -> float:
    """把 '1.2万' / '500+' / '5000' 之类转换成数值用于排序。"""
    if not s:
        return 0.0
    s = s.replace("+", "").strip()
    try:
        if "万" in s:
            return float(s.replace("万", "")) * 10000
        return float(s)
    except ValueError:
        return 0.0


async def sycm_snapshot(page: Page, output_dir: Path) -> None:
    """生意参谋抓取模式：拦截所有 sycm.taobao.com 的 XHR JSON 响应，落盘保存。

    用法：脚本启动后，你在弹出的浏览器里手动导航到任何生意参谋页面
    （商品店铺榜 / 搜索词查询 / 人群画像等），等数据加载完毕后，
    回到终端按 Enter 结束，所有 JSON 响应会被分类保存到本地。
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    captured: List[dict] = []

    async def on_response(resp: Response):
        url = resp.url
        if "sycm.taobao.com" not in url:
            return
        ct = (resp.headers.get("content-type") or "").lower()
        if "json" not in ct:
            return
        try:
            body = await resp.json()
        except Exception:
            return

        # 用 URL path 派生文件名
        path = re.sub(r"[^a-zA-Z0-9_\-]", "_", url.split("?")[0].split("//")[-1])[:80]
        ts = int(time.time() * 1000)
        fname = output_dir / f"{ts}_{path}.json"
        try:
            fname.write_text(
                json.dumps({"url": url, "body": body}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            captured.append({"url": url, "file": str(fname.name)})
            print(f"  [snapshot] {fname.name}  ({len(json.dumps(body))} bytes)")
        except Exception as e:
            print(f"  [warn] save failed: {e}")

    page.on("response", on_response)

    # 直接打开生意参谋首页
    print("\n[>] 打开生意参谋首页 sycm.taobao.com ...")
    try:
        await page.goto("https://sycm.taobao.com/", wait_until="domcontentloaded", timeout=20000)
    except Exception as e:
        print(f"[!] 首页打开异常（不影响后续手动操作）：{e}")

    print("\n" + "=" * 70)
    print("生意参谋抓取模式 — 操作指引")
    print("=" * 70)
    print("1. 在弹出的浏览器里，手动导航到你想抓的任意生意参谋页面，例如：")
    print("   - 市场 > 商品店铺榜  (女装球衣 类目精确销量 Top 榜)")
    print("   - 市场 > 搜索词查询  (球衣相关热词热度/转化)")
    print("   - 流量 > 来源分析     (我的店铺流量结构)")
    print("   - 人群 > 画像分析     (购买人群年龄/地域/消费层级)")
    print()
    print("2. 等页面数据完全加载（看到表格/图表都出来）")
    print()
    print("3. 想多抓几个页面就继续切换，脚本会自动累积保存")
    print()
    print(f"4. 完成后回到这里，按 Enter 结束。所有 JSON 会保存到：")
    print(f"   {output_dir}")
    print("=" * 70)
    input("\n按 Enter 结束抓取 > ")

    # 落一个索引文件
    (output_dir / "_index.json").write_text(
        json.dumps(captured, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n[+] 共抓取 {len(captured)} 个 JSON 响应。")
    print(f"[+] 索引文件：{output_dir / '_index.json'}")
    print(f"[+] 下一步：用 jq/Excel 解析这些 JSON 即可（每个文件首层一般是 data.list 或 data.data）。")


async def run(args: argparse.Namespace) -> None:
    async with async_playwright() as p:
        # 使用持久化 user data，复用上次登录
        storage_state = str(STATE_FILE) if STATE_FILE.exists() else None
        browser = await p.chromium.launch(
            headless=not args.headful,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
        )
        context = await browser.new_context(
            storage_state=storage_state,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 900},
            locale="zh-CN",
        )
        # 简单绕过 webdriver 检测
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )

        page = await context.new_page()
        await ensure_login(context, page)

        # 生意参谋抓取模式 -- 拦截 XHR 直接落 JSON
        if args.mode == "sycm":
            output_dir = Path(__file__).parent / "sycm_snapshots" / time.strftime("%Y%m%d_%H%M%S")
            await sycm_snapshot(page, output_dir)
            await context.close()
            await browser.close()
            return

        all_products: List[Product] = []
        for i in range(1, args.pages + 1):
            items = await search_and_extract(page, args.keyword, i)
            all_products.extend(items)
            if i < args.pages:
                # 随机间隔，降低风控
                await page.wait_for_timeout(random.randint(2000, 4500))

        # 按销量重新排序 (淘宝默认已是销量排序，这里只是兜底)
        all_products.sort(key=lambda x: parse_sold(x.sold), reverse=True)
        top = all_products[: args.top]
        for idx, p_item in enumerate(top, 1):
            p_item.rank = idx

        # 导出 CSV
        csv_path = f"{args.output}_{args.keyword}.csv"
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=list(asdict(top[0]).keys()) if top else [])
            writer.writeheader()
            for p_item in top:
                writer.writerow(asdict(p_item))

        # 导出 Excel
        xlsx_path = f"{args.output}_{args.keyword}.xlsx"
        try:
            import pandas as pd
            df = pd.DataFrame([asdict(p) for p in top])
            df.to_excel(xlsx_path, index=False)
            print(f"[+] Excel 导出 -> {xlsx_path}")
        except ImportError:
            print("[i] pandas/openpyxl 未安装，跳过 Excel 导出。CSV 已生成。")

        print(f"[+] CSV 导出 -> {csv_path}")
        print(f"[+] 抓取完成，共 Top {len(top)} 件商品。")

        await context.close()
        await browser.close()


def main():
    parser = argparse.ArgumentParser(
        description="抓取淘宝公开搜索 / 生意参谋的销量 Top N 商品",
    )
    parser.add_argument(
        "--mode",
        choices=["market", "sycm"],
        default="market",
        help=(
            "抓取模式: "
            "market = 淘宝公开搜索 (受风控限制，销量为区间值); "
            "sycm = 生意参谋 XHR 拦截 (需要商家登录，数据精确)"
        ),
    )
    parser.add_argument("--keyword", default="女装球衣", help="[market 模式] 搜索关键词")
    parser.add_argument("--top", type=int, default=10, help="[market 模式] 保留前 N 名")
    parser.add_argument("--pages", type=int, default=1, help="[market 模式] 翻几页")
    parser.add_argument("--output", default="taobao_top", help="[market 模式] 输出文件前缀")
    parser.add_argument(
        "--headful", action="store_true",
        help="显示浏览器窗口 (首次登录 / sycm 模式必须开启)",
    )
    args = parser.parse_args()

    if args.mode == "sycm":
        args.headful = True  # 生意参谋必须可见浏览器，让用户手动导航

    if not STATE_FILE.exists() and not args.headful:
        print("[i] 检测到首次运行，自动开启 --headful 以便登录。")
        args.headful = True

    asyncio.run(run(args))


if __name__ == "__main__":
    main()
