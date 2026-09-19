# -*- coding: utf-8 -*-
"""得物搬砖套利 · 利润计算引擎。

得物卖家到手价计算（参考得物卖家费用结构）：
    到手价 = 卖出价 × (1 - 技术服务费率 - 转账服务费率) - 查验费 - 鉴别费 - 包装费
套利利润：
    利润 = 得物到手价 - 平台最低买入价 - 运费
"""
from __future__ import annotations

import re
from typing import Dict, Optional

# 得物卖家费用默认值（可在设置中覆盖）
DEFAULT_FEES: Dict[str, float] = {
    "tech_fee_rate": 0.05,       # 技术服务费率（%）
    "transfer_fee_rate": 0.01,   # 转账服务费率（%）
    "check_fee": 8.0,            # 查验费（元）
    "discern_fee": 5.0,          # 鉴别费（元）
    "package_fee": 2.0,          # 包装服务费（元）
    "shipping_fee": 10.0,        # 运费合计（平台买入 + 寄到得物，元）
}

# 各平台进货常用优先级（用于排序，数字小优先）
PLATFORM_ORDER = {"拼多多": 1, "淘宝": 2, "天猫": 2, "京东": 3, "苏宁易购": 4, "唯品会": 5}

# 标题相关性过滤：这些修饰词不算「核心词」
_STOP_WORDS = ["国行全新", "国行", "全新", "正品", "正版", "官方", "原装", "专柜", "2025款", "2024款", "新款"]


def title_match(dewu_title: str, quote_title: str) -> bool:
    """判断得物标题与平台报价标题是否相关（共享核心词）。

    用于过滤「iPhone 17 Pro → 换电池服务」这类货号模糊匹配导致的误匹配。
    """
    if not dewu_title or not quote_title:
        return False
    core = dewu_title
    for s in _STOP_WORDS:
        core = core.replace(s, " ")
    words = [w for w in re.split(r"[\s\-/·、,，.]+", core) if len(w) >= 2]
    if not words:
        return True  # 无法提取核心词时不拦截
    return any(w.lower() in quote_title.lower() for w in words[:5])


def dewu_net_price(sell_price: float, fees: Optional[Dict[str, float]] = None) -> float:
    """得物到手价（元）。"""
    f = {**DEFAULT_FEES, **(fees or {})}
    rate = f["tech_fee_rate"] + f["transfer_fee_rate"]
    fixed = f["check_fee"] + f["discern_fee"] + f["package_fee"]
    return round(sell_price * (1 - rate) - fixed, 2)


def arbitrage_profit(dewu_sell: float, platform_buy: float,
                     fees: Optional[Dict[str, float]] = None) -> float:
    """套利利润（元）= 得物到手价 - 平台买入价 - 运费。"""
    f = {**DEFAULT_FEES, **(fees or {})}
    net = dewu_net_price(dewu_sell, f)
    return round(net - platform_buy - f["shipping_fee"], 2)


def profit_rate(profit: float, platform_buy: float) -> float:
    """利润率（%）。"""
    if not platform_buy:
        return 0.0
    return round(profit / platform_buy * 100, 1)


def evaluate_opportunity(dewu_sell: float, quotes: list, fees: Optional[Dict[str, float]] = None,
                         min_price: float = 1.0) -> dict:
    """对一件商品的多平台报价做套利评估。

    dewu_sell: 得物卖出价（元）
    quotes: 各平台报价列表 [{platform, price, sales, link}]
    min_price: 过滤低于此价的异常报价（如 0.01 为缺货/下架标记）
    返回：{bestBuy, netPrice, profit, profitRate, quotes 按利润排序}
    """
    f = {**DEFAULT_FEES, **(fees or {})}
    net = dewu_net_price(dewu_sell, f)
    results = []
    for q in quotes:
        price = q.get("price")
        if not price or price < min_price:
            continue
        profit = round(net - price - f["shipping_fee"], 2)
        results.append({
            **q,
            "profit": profit,
            "profitRate": profit_rate(profit, price),
        })
    results.sort(key=lambda x: (x["profitRate"], x["profit"]), reverse=True)
    best = results[0] if results else None
    return {
        "netPrice": net,
        "bestBuy": best,
        "profit": best["profit"] if best else None,
        "profitRate": best["profitRate"] if best else None,
        "quotes": results,
    }
