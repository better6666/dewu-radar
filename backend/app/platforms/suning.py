# -*- coding: utf-8 -*-
"""苏宁易购 adapter（评级 A：无登录、无签名、curl 直连可抓价）。

搜索：search.suning.com/emall/searchV1Product.do（服务端渲染 HTML）
价格：ds.suning.com/ds/generalForTile/{item}-025-{type}-{supplierCode}-1--{callback}.json
详见 电商价格接口调研报告.md。
"""
from __future__ import annotations

import html
import re
import ssl
from typing import Any, Dict, List

import requests

from .base import PlatformAdapter

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

SEARCH_URL = "https://search.suning.com/emall/searchV1Product.do"
PRICE_URL = "https://ds.suning.com/ds/generalForTile/{item}-025-{type}-{supplierCode}-1--ds0000000001234.json"

_LI_RE = re.compile(r"<li\b[^>]*>.*?</li>", re.S)


class SuningAdapter(PlatformAdapter):
    name = "苏宁易购"

    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": UA})

    def search(self, keyword: str, limit: int = 10) -> List[Dict[str, Any]]:
        items = self._search(keyword)
        if not items:
            return []
        self._fill_prices(items)
        quotes = []
        for it in items:
            if it.get("price") is None:
                continue
            quotes.append(self.quote(it["title"], it["price"], it.get("reviews"), it["link"], it.get("partnumber")))
        return quotes[:limit]

    # ------------------------------------------------------------------
    def _search(self, keyword: str) -> List[Dict[str, Any]]:
        r = self.session.get(SEARCH_URL, params={"keyword": keyword, "pg": "01"}, timeout=self.timeout)
        r.raise_for_status()
        text = r.text
        items = []
        for li in _LI_RE.findall(text):
            datasku_m = re.search(r'datasku="([^"]*)"', li)
            if not datasku_m:
                continue
            parts = datasku_m.group(1).split("|")
            if len(parts) < 6:
                continue
            brand_m = re.search(r'brand_id="([^"]*)"', li)
            group_m = re.search(r'mdmGroupId="([^"]*)"', li)
            # 标题：title-selling-point 的 a 标签内第一个文本（排除隐藏 em）
            title_m = re.search(r'title-selling-point[^>]*>\s*<a[^>]*>\s*([^<]+)', li)
            title = html.unescape(title_m.group(1)).strip() if title_m else ""
            if not title:
                continue
            reviews_m = re.search(r"<i>([\d.万+]+)</i>\s*评价", li)
            reviews = reviews_m.group(1) if reviews_m else None
            items.append({
                "partnumber": parts[0],
                "type": parts[2],
                "supplierCode": parts[5],
                "threegroupId": group_m.group(1) if group_m else "",
                "brandId": brand_m.group(1) if brand_m else "",
                "title": title,
                "reviews": reviews,
                "link": f"https://product.suning.com/{parts[5]}/{parts[0]}.html",
            })
        return items

    def _fill_prices(self, items: List[Dict[str, Any]]) -> None:
        """逐条查价格（苏宁价格接口一次可查多个 item，但逐条更稳健）。"""
        for it in items:
            try:
                it["price"] = self._price(it)
            except Exception:  # noqa: BLE001
                it["price"] = None

    def _price(self, it: Dict[str, Any]):
        part18 = it["partnumber"].zfill(18)
        item = f"{part18}_____{it['threegroupId']}_{it['brandId']}__"
        url = PRICE_URL.format(item=item, type=it["type"] or "", supplierCode=it["supplierCode"])
        r = self.session.get(url, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        rs = data.get("rs") or []
        if rs and rs[0].get("price"):
            return float(rs[0]["price"])
        return None
