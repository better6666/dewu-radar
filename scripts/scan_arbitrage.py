# -*- coding: utf-8 -*-
"""得物搬砖套利扫描 · 主流程。

抓得物热门商品（含货号）→ 用货号去各平台搜索比价 → 计算套利利润 → 输出机会列表。

用法：
    python scripts/scan_arbitrage.py [--pages 3] [--min-rate 5.0] [--out path.json]
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.arbitrage import evaluate_opportunity, title_match  # noqa: E402
from app.platforms.dewu import DewuAdapter  # noqa: E402

# 各平台 adapter（按调研结果逐个接入）
from app.platforms.registry import get_adapters  # noqa: E402


def scan(pages: int = 3, min_rate: float = 3.0, max_rate: float = 200.0, limit: int = 20) -> list:
    dewu = DewuAdapter()
    adapters = get_adapters()
    hot = dewu.hot_products(pages=pages, limit=limit)
    print(f"[scan] 得物热门商品 {len(hot)} 个，待比价平台 {len(adapters)} 个：{[a.name for a in adapters]}")

    opportunities = []
    for p in hot:
        article = (p.get("articleNumber") or "").strip()
        title = p.get("title") or ""
        if not article or article == title:
            continue
        dewu_sell = p.get("price")
        if not dewu_sell:
            continue

        quotes = []
        for ad in adapters:
            try:
                qs = ad.search(article, limit=8)
                # 标题相关性过滤：避免货号模糊匹配误配到配件/维修等
                quotes.extend(q for q in qs if title_match(title, q.get("title", "")))
                time.sleep(0.5)
            except Exception as e:  # noqa: BLE001
                print(f"[scan] {ad.name} 搜索 {article} 失败: {e}")

        if not quotes:
            continue

        r = evaluate_opportunity(dewu_sell, quotes)
        if r["profit"] is not None and r["profit"] > 0 and min_rate <= r["profitRate"] <= max_rate:
            opportunities.append({
                "articleNumber": article,
                "title": title,
                "logoUrl": p.get("logoUrl"),
                "dewuPrice": dewu_sell,
                "dewuSales": p.get("soldCountText"),
                "netPrice": r["netPrice"],
                "bestBuy": r["bestBuy"],
                "profit": r["profit"],
                "profitRate": r["profitRate"],
                "quotes": r["quotes"],
            })

    opportunities.sort(key=lambda x: (x["profitRate"], x["profit"]), reverse=True)
    return opportunities


def main() -> None:
    args = sys.argv[1:]
    pages = int(args[args.index("--pages") + 1]) if "--pages" in args else 3
    min_rate = float(args[args.index("--min-rate") + 1]) if "--min-rate" in args else 3.0
    out = args[args.index("--out") + 1] if "--out" in args else None

    opps = scan(pages=pages, min_rate=min_rate)
    print(f"\n[scan] 发现 {len(opps)} 个套利机会（利润率 ≥ {min_rate}%）：")
    for o in opps[:20]:
        b = o["bestBuy"]
        print(f"  {o['articleNumber']}  {o['title'][:24]}  "
              f"得物¥{o['dewuPrice']} → {b['platform']}¥{b['price']}  利润¥{o['profit']} ({o['profitRate']}%)")

    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(json.dumps({"opportunities": opps, "updatedAt": time.time()},
                                        ensure_ascii=False), encoding="utf-8")
        print(f"[scan] 已写入 {out}")


if __name__ == "__main__":
    main()
