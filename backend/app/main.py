# -*- coding: utf-8 -*-
"""得物雷达 FastAPI 后端入口。"""
from __future__ import annotations

import json
import logging
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import DEWU_PROXY, DEWU_TIMEOUT
from .db import get_db
from .dewu_client import (DewuClient, DewuError, merge_skus, parse_detail,
                          parse_discover, parse_prices)
from .notify import Notifier, build_alert_message, load_config
from .scheduler import get_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("dewu")

app = FastAPI(title="得物雷达", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

_client = DewuClient(proxy=DEWU_PROXY, timeout=DEWU_TIMEOUT)


class WatchBody(BaseModel):
    watched: bool = True
    alert_price: float = 0.0


class CollectBody(BaseModel):
    pages: int = 2
    limit: int = 20


class SettingsBody(BaseModel):
    config: dict


class QuoteBody(BaseModel):
    article_number: str
    platform: str
    price: float
    sales: str = ""
    link: str = ""
    note: str = ""


# snake_case → camelCase 字段映射（统一前后端契约）
_FIELD_MAP = {
    "spu_id": "spuId",
    "sub_title": "subTitle",
    "logo_url": "logoUrl",
    "article_number": "articleNumber",
    "auth_price": "authPrice",
    "sell_date": "sellDate",
    "sold_count_text": "soldCountText",
    "alert_price": "alertPrice",
    "latest_price": "latestPrice",
    "min_price": "minPrice",
    "max_price": "maxPrice",
    "price_change": "priceChange",
    "price_change_pct": "priceChangePct",
    "premium_pct": "premiumPct",
    "created_at": "createdAt",
    "updated_at": "updatedAt",
}


def _row_to_dict(row) -> dict:
    d = dict(row)
    if d.get("skus_json"):
        try:
            d["skus"] = json.loads(d["skus_json"])
        except json.JSONDecodeError:
            d["skus"] = []
    d.pop("skus_json", None)
    for snake, camel in _FIELD_MAP.items():
        if snake in d:
            d[camel] = d.pop(snake)
    return d


@app.get("/api/health")
def health():
    return {"status": "ok", "proxy": bool(DEWU_PROXY)}


@app.get("/api/search")
def search(q: str = Query(..., min_length=1), page: int = 0, limit: int = 20):
    """搜索得物商品。"""
    try:
        data = _client.search(q, page=page, limit=limit)
    except DewuError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=repr(e))

    d = data.get("data") or {}
    items = []
    for it in d.get("productList") or []:
        items.append({
            "spuId": it.get("spuId"),
            "title": it.get("title"),
            "subTitle": it.get("subTitle"),
            "logoUrl": it.get("logoUrl"),
            "articleNumber": it.get("articleNumber"),
            "price": round(it["price"] / 100, 2) if it.get("price") else None,
            "soldNum": it.get("soldNum"),
        })
    return {"total": d.get("total"), "items": items}


@app.post("/api/collect")
def collect(body: CollectBody):
    """从得物首页推荐流批量采集热门商品入库。"""
    db = get_db()
    collected, failed = [], []
    last_id = 1
    try:
        for _ in range(max(1, body.pages)):
            data = _client.discover(last_id=last_id, limit=body.limit)
            items = parse_discover(data)
            if not items:
                break
            for it in items:
                try:
                    db.upsert_product(it, source="discover")
                    db.record_price(it["spuId"], it.get("price"),
                                    json.dumps(it, ensure_ascii=False, default=str))
                    collected.append(it["spuId"])
                except Exception as e:  # noqa: BLE001
                    failed.append({"spuId": it.get("spuId"), "error": repr(e)})
            last_id = (data.get("data") or {}).get("lastId") or (last_id + 1)
    except DewuError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=repr(e))
    return {"collected": len(collected), "failed": failed}


@app.post("/api/products/fetch")
def fetch_product(spu_id: Optional[str] = None, keyword: Optional[str] = None):
    """抓取并入库一个商品（通过 spuId 或关键词搜索第一个结果）。"""
    if not spu_id and not keyword:
        raise HTTPException(status_code=400, detail="需提供 spuId 或 keyword")
    try:
        if not spu_id:
            search_data = _client.search(keyword)
            plist = (search_data.get("data") or {}).get("productList") or []
            if not plist:
                raise HTTPException(status_code=404, detail=f"未找到关键词「{keyword}」对应的商品")
            spu_id = str(plist[0]["spuId"])

        result = _client.fetch_product(spu_id)
        info = parse_detail(result["detail"])
        prices = parse_prices(result["prices"])
        info["skus"] = merge_skus(info["skus"], prices)

        db = get_db()
        product_id = db.upsert_product(info)

        min_price = None
        if prices:
            for sku in prices:
                vals = [v for v in sku.values() if isinstance(v, (int, float))]
                if vals:
                    m = min(vals)
                    min_price = m if min_price is None else min(min_price, m)
        db.record_price(spu_id, min_price, json.dumps(
            {"detail": result["detail"], "prices": result["prices"]}, ensure_ascii=False, default=str))

        return {"productId": product_id, "spuId": spu_id, "info": info, "prices": prices}
    except DewuError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=repr(e))


def _enrich(row) -> dict:
    """为商品附加涨跌、迷你趋势、溢价率等展示字段。"""
    db = get_db()
    d = _row_to_dict(row)
    hist = db.price_history(row["spu_id"], limit=60)
    prices = [h["price"] for h in hist if h["price"] is not None]
    d["sparkline"] = prices[-24:]
    if len(prices) >= 2:
        prev, last = prices[-2], prices[-1]
        d["priceChange"] = round(last - prev, 2)
        d["priceChangePct"] = round((last - prev) / prev * 100, 2) if prev else 0.0
    else:
        d["priceChange"] = 0.0
        d["priceChangePct"] = 0.0
    if row["latest_price"] and row["auth_price"]:
        d["premiumPct"] = round((row["latest_price"] - row["auth_price"]) / row["auth_price"] * 100, 1)
    else:
        d["premiumPct"] = None
    return d


@app.get("/api/stats")
def stats():
    """仪表盘统计指标。"""
    db = get_db()
    rows = db.list_products()
    total = len(rows)
    watched = sum(1 for r in rows if r["watched"])
    up = down = 0
    premiums = []
    for r in rows:
        hist = db.price_history(r["spu_id"], limit=2)
        prices = [h["price"] for h in hist if h["price"] is not None]
        if len(prices) >= 2:
            if prices[-1] > prices[-2]:
                up += 1
            elif prices[-1] < prices[-2]:
                down += 1
        if r["latest_price"] and r["auth_price"]:
            premiums.append((r["latest_price"] - r["auth_price"]) / r["auth_price"] * 100)
    avg_premium = round(sum(premiums) / len(premiums), 1) if premiums else None
    return {"total": total, "watched": watched, "up": up, "down": down, "avgPremium": avg_premium}


@app.get("/api/products")
def list_products(watched: bool = False, q: str = ""):
    db = get_db()
    rows = db.list_products(watched_only=watched, keyword=q)
    return {"items": [_enrich(r) for r in rows]}


@app.get("/api/products/{product_id}")
def get_product(product_id: int):
    db = get_db()
    row = db.get_product(product_id)
    if not row:
        raise HTTPException(status_code=404, detail="商品不存在")
    d = _enrich(row)
    d["history"] = [{"price": r["price"], "ts": r["created_at"]}
                    for r in db.price_history(row["spu_id"])]
    return d


@app.post("/api/products/{product_id}/watch")
def set_watch(product_id: int, body: WatchBody):
    db = get_db()
    if not db.get_product(product_id):
        raise HTTPException(status_code=404, detail="商品不存在")
    db.set_watch(product_id, body.watched, body.alert_price)
    return {"ok": True}


@app.get("/api/products/{product_id}/history")
def get_history(product_id: int, limit: int = 200):
    db = get_db()
    row = db.get_product(product_id)
    if not row:
        raise HTTPException(status_code=404, detail="商品不存在")
    return {"items": [{"price": r["price"], "ts": r["created_at"]}
                      for r in db.price_history(row["spu_id"], limit=limit)]}


@app.post("/api/poll")
def poll():
    """手动触发一次监控轮询。"""
    scheduler = get_scheduler()
    return scheduler.poll_once()


@app.get("/api/settings")
def get_settings():
    """读取应用设置（通知配置等）。"""
    db = get_db()
    return {"notify": load_config(db)}


@app.post("/api/settings")
def set_settings(body: SettingsBody):
    """保存应用设置（通知配置等）。"""
    db = get_db()
    cfg = body.config.get("notify", {})
    db.set_setting("notify_config", json.dumps(cfg, ensure_ascii=False))
    return {"ok": True}


@app.post("/api/notify/test")
def notify_test():
    """发送一条测试通知，验证渠道配置。"""
    db = get_db()
    cfg = load_config(db)
    notifier = Notifier(cfg)
    res = notifier.send("得物雷达测试", "这是一条测试推送，说明通知渠道配置成功 ✅")
    return res


@app.get("/api/alerts")
def list_alerts(limit: int = 100):
    """列出价格告警记录。"""
    db = get_db()
    return {"items": [_row_to_dict(r) for r in db.list_alerts(limit=limit)]}


@app.get("/api/arbitrage")
def arbitrage(pages: int = 3, min_rate: float = 0.0, max_rate: float = 200.0):
    """扫描得物搬砖套利机会：得物热门商品 → 各平台比价 → 利润排序。"""
    from .arbitrage import DEFAULT_FEES, evaluate_opportunity, title_match
    from .platforms.dewu import DewuAdapter
    from .platforms.registry import get_adapters

    db = get_db()
    dewu = DewuAdapter(_client)
    adapters = get_adapters()
    hot = dewu.hot_products(pages=pages)
    opportunities = []
    for p in hot:
        article = (p.get("articleNumber") or "").strip()
        title = p.get("title") or ""
        dewu_sell = p.get("price")
        if not article or article == title or not dewu_sell:
            continue
        quotes = []
        for ad in adapters:
            try:
                qs = ad.search(article, limit=8)
                quotes.extend(q for q in qs if title_match(title, q.get("title", "")))
            except Exception:  # noqa: BLE001
                continue
        # 手动报价（覆盖自动抓取不可行的平台：淘宝/京东/拼多多/唯品会）
        for mq in db.manual_quotes(article):
            quotes.append({
                "platform": mq["platform"],
                "title": f"{mq['platform']} 手动报价",
                "price": mq["price"],
                "sales": mq["sales"],
                "link": mq["link"],
                "skuId": None,
                "manual": True,
            })
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
    return {"opportunities": opportunities, "fees": DEFAULT_FEES, "platforms": [a.name for a in adapters]}


@app.post("/api/quotes")
def add_quote(body: QuoteBody):
    """添加/更新手动报价（用于自动抓取不可行的平台）。"""
    db = get_db()
    quote_id = db.upsert_manual_quote(
        body.article_number, body.platform, body.price, body.sales, body.link, body.note)
    return {"ok": True, "quoteId": quote_id}


@app.get("/api/quotes/{article_number}")
def get_quotes(article_number: str):
    """查询某货号的手动报价。"""
    db = get_db()
    return {"items": [_row_to_dict(r) for r in db.manual_quotes(article_number)]}


@app.delete("/api/quotes/{quote_id}")
def delete_quote(quote_id: int):
    """删除手动报价。"""
    db = get_db()
    db.delete_manual_quote(quote_id)
    return {"ok": True}


@app.on_event("startup")
def startup():
    get_scheduler().start()
    logger.info("得物雷达后端启动完成")


@app.on_event("shutdown")
def shutdown():
    get_scheduler().stop()
