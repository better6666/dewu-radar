# -*- coding: utf-8 -*-
"""得物 adapter：封装 dewu_client，提供「卖出价」与「货号」。"""
from __future__ import annotations

from typing import Any, Dict, List

from ..dewu_client import DewuClient, parse_discover
from .base import PlatformAdapter


class DewuAdapter(PlatformAdapter):
    name = "得物"

    def __init__(self, client: DewuClient = None):
        self.client = client or DewuClient()

    def hot_products(self, pages: int = 3, limit: int = 20) -> List[Dict[str, Any]]:
        """抓得物首页热门商品（含货号、卖出价、销量），作为套利候选。"""
        out = []
        last_id = 1
        for _ in range(pages):
            try:
                data = self.client.discover(last_id=last_id, limit=limit)
            except Exception:
                break
            items = parse_discover(data)
            if not items:
                break
            out.extend(items)
            last_id = (data.get("data") or {}).get("lastId") or (last_id + 1)
        return out

    def search(self, keyword: str, limit: int = 10) -> List[Dict[str, Any]]:
        # 得物作为「卖出方」，搜索主要给本地手动比价用
        return []
