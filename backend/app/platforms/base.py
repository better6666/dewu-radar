# -*- coding: utf-8 -*-
"""多平台 adapter 基类。每个电商平台实现一个 adapter，统一搜索接口。"""
from __future__ import annotations

from typing import Any, Dict, List


class PlatformAdapter:
    """平台抓取 adapter 接口。

    每个平台实现 search(keyword) -> list[quote]。
    quote 结构：{"platform", "title", "price", "sales", "link", "skuId"}
    """

    name: str = "unknown"

    def search(self, keyword: str, limit: int = 10) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def quote(self, title, price, sales, link, sku_id=None) -> Dict[str, Any]:
        return {
            "platform": self.name,
            "title": title,
            "price": _yuan(price),
            "sales": sales,
            "link": link,
            "skuId": sku_id,
        }


def _yuan(v):
    if v is None:
        return None
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None
