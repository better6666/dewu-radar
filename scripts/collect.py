# -*- coding: utf-8 -*-
"""得物雷达 · 独立数据采集脚本（用于 GitHub Actions 定时抓取）。

复用 backend 的得物接口算法（签名 + RSA/AES），抓取首页推荐流（数据中心 IP 可抓），
生成静态 JSON 到 frontend/public/data/，供 GitHub Pages 前端直接读取。

用法：
    python scripts/collect.py

环境变量（可选，用于推送通知，通常通过 GitHub Secrets 注入）：
    DINGTALK_WEBHOOK   钉钉机器人 Webhook
    BARK_URL           Bark 推送地址（https://api.day.app/你的key）
    SERVERCHAN_KEY     Server酱 SendKey
    WEBHOOK_URL        自定义 Webhook（接收 JSON {"title","body"}）

配置（scripts/watchlist.json）：
    {"watch": [{"spuId": "...", "alertPrice": 400}], "collectPages": 4}
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# 复用 backend 的得物客户端算法
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

import requests  # noqa: E402
from app.dewu_client import DewuClient, DewuError, parse_discover  # noqa: E402

OUT_DIR = ROOT / "frontend" / "public" / "data"
WATCHLIST_PATH = ROOT / "scripts" / "watchlist.json"
HISTORY_PATH = OUT_DIR / "history.json"
ALERTS_PATH = OUT_DIR / "alerts.json"


# ---------------------------------------------------------------------------
# 通知
# ---------------------------------------------------------------------------
def notify(title: str, body: str) -> bool:
    """按环境变量配置的渠道发送通知，返回是否成功。"""
    ok = False
    ding = os.environ.get("DINGTALK_WEBHOOK")
    bark = os.environ.get("BARK_URL")
    sckey = os.environ.get("SERVERCHAN_KEY")
    hook = os.environ.get("WEBHOOK_URL")
    try:
        if ding:
            r = requests.post(ding, json={"msgtype": "markdown", "markdown": {"title": title, "text": f"### {title}\n\n{body}"}}, timeout=10)
            ok = r.json().get("errcode") == 0
        if bark:
            r = requests.post(f"{bark.rstrip('/')}/{title}/{body}", timeout=10)
            ok = r.status_code == 200
        if sckey:
            r = requests.post(f"https://sctapi.ftqq.com/{sckey}.send", data={"title": title, "desp": body}, timeout=10)
            ok = r.status_code == 200
        if hook:
            r = requests.post(hook, json={"title": title, "body": body}, timeout=10)
            ok = r.status_code in (200, 204)
    except Exception as e:  # noqa: BLE001
        print(f"[notify] 发送失败: {e}")
    return ok


def _yuan(v):
    if v is None:
        return None
    try:
        return round(float(v) / 100.0, 2)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 历史 / 告警累积
# ---------------------------------------------------------------------------
def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return default
    return default


def load_history() -> dict:
    return load_json(HISTORY_PATH, {})


def load_alerts() -> list:
    return load_json(ALERTS_PATH, {"items": []}).get("items", [])


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main() -> None:
    cfg = load_json(WATCHLIST_PATH, {"watch": [], "collectPages": 4})
    pages = int(cfg.get("collectPages", 4) or 4)
    watch = cfg.get("watch", []) or []

    client = DewuClient()
    history = load_history()
    alerts = load_alerts()
    now = time.time()

    # 1) 抓首页流
    products = []          # 本次抓到的商品（含价格）
    seen = set()
    last_id = 1
    for page in range(pages):
        try:
            data = client.discover(last_id=last_id, limit=20)
        except DewuError as e:
            print(f"[collect] 第{page + 1}页抓取失败: {e}")
            break
        items = parse_discover(data)
        if not items:
            break
        for it in items:
            spu = it["spuId"]
            if spu in seen:
                continue
            seen.add(spu)
            products.append(it)
        last_id = (data.get("data") or {}).get("lastId") or (last_id + 1)
        time.sleep(1)
    print(f"[collect] 抓取到 {len(products)} 个商品（{pages} 页）")

    # 2) 监控列表：标记 watched + 告警价；若不在首页流中则尝试抓详情
    watch_map = {str(w["spuId"]): float(w.get("alertPrice") or 0) for w in watch}
    found_watch = set()
    for it in products:
        ap = watch_map.get(it["spuId"])
        if ap is not None:
            it["watched"] = 1
            it["alertPrice"] = ap
            found_watch.add(it["spuId"])

    # 监控中但未出现在首页流的商品，尝试单独抓详情（数据中心 IP 可能被风控）
    for spu, ap in watch_map.items():
        if spu in found_watch or spu in seen:
            continue
        try:
            detail = client.product_detail(spu)
            d = (detail.get("data") or {}).get("detail") or {}
            products.append({
                "spuId": spu,
                "title": d.get("title"),
                "subTitle": d.get("subTitle"),
                "logoUrl": d.get("logoUrl"),
                "articleNumber": d.get("articleNumber"),
                "authPrice": _yuan(d.get("authPrice")),
                "price": None,
                "sellDate": d.get("sellDate"),
                "brand": None,
                "soldCountText": None,
                "skus": [],
                "watched": 1,
                "alertPrice": ap,
            })
            seen.add(spu)
        except Exception as e:  # noqa: BLE001
            print(f"[collect] 监控商品 {spu} 抓详情失败: {e}")

    # 3) 累积价格历史 + 计算涨跌/溢价
    alerts_to_send = []
    for it in products:
        spu = it["spuId"]
        price = it.get("price")
        if price is None:
            it["latestPrice"] = None
            it["priceChange"] = 0.0
            it["priceChangePct"] = 0.0
            it["premiumPct"] = None
            it["sparkline"] = [p["price"] for p in history.get(spu, []) if p.get("price") is not None][-24:]
            continue

        hist = history.get(spu, [])
        if not hist or hist[-1].get("price") != price:
            hist.append({"price": price, "ts": now})
            # 限制历史长度
            if len(hist) > 200:
                hist = hist[-200:]
            history[spu] = hist

        prices = [p["price"] for p in hist if p.get("price") is not None]
        it["latestPrice"] = price
        it["minPrice"] = min(prices) if prices else price
        it["maxPrice"] = max(prices) if prices else price
        it["sparkline"] = prices[-24:]
        if len(prices) >= 2:
            prev, last = prices[-2], prices[-1]
            it["priceChange"] = round(last - prev, 2)
            it["priceChangePct"] = round((last - prev) / prev * 100, 2) if prev else 0.0
        else:
            it["priceChange"] = 0.0
            it["priceChangePct"] = 0.0
        auth = it.get("authPrice")
        it["premiumPct"] = round((price - auth) / auth * 100, 1) if (price and auth) else None

        # 告警检测
        ap = it.get("alertPrice")
        if ap and it.get("watched") and price < ap:
            # 避免重复告警：最近 6 小时内已告警过则跳过
            recent = [a for a in alerts if a.get("spuId") == spu and now - a.get("ts", 0) < 6 * 3600]
            if not recent:
                title = f"📉 {it.get('title') or spu} 跌破告警价"
                body = (f"商品：{it.get('title') or '—'}\n货号：{it.get('articleNumber') or '—'}\n"
                        f"当前价：¥{price:.2f}\n告警价：¥{ap:.2f}\n降幅：¥{ap - price:.2f}")
                sent = notify(title, body)
                alerts_to_send.append({"spuId": spu, "title": it.get("title"), "price": price,
                                       "alertPrice": ap, "ts": now, "sent": sent})
                print(f"[alert] {title} sent={sent}")

    alerts = (alerts_to_send + alerts)[:200]

    # 4) 组装商品列表（对齐前端 camelCase 契约）
    out_items = []
    for it in products:
        item = {
            "id": abs(hash(it["spuId"])) % (10 ** 9),   # 稳定 id，仅供前端 key
            "spuId": it["spuId"],
            "title": it.get("title"),
            "subTitle": it.get("subTitle"),
            "logoUrl": it.get("logoUrl"),
            "articleNumber": it.get("articleNumber"),
            "authPrice": it.get("authPrice"),
            "sellDate": it.get("sellDate"),
            "brand": it.get("brand"),
            "soldCountText": it.get("soldCountText"),
            "source": "discover",
            "skus": it.get("skus", []),
            "watched": it.get("watched", 0),
            "alertPrice": it.get("alertPrice", 0),
            "latestPrice": it.get("latestPrice"),
            "minPrice": it.get("minPrice"),
            "maxPrice": it.get("maxPrice"),
            "sparkline": it.get("sparkline", []),
            "priceChange": it.get("priceChange", 0.0),
            "priceChangePct": it.get("priceChangePct", 0.0),
            "premiumPct": it.get("premiumPct"),
        }
        out_items.append(item)

    # 5) 统计
    total = len(out_items)
    watched_n = sum(1 for i in out_items if i["watched"])
    up = sum(1 for i in out_items if (i["priceChange"] or 0) > 0)
    down = sum(1 for i in out_items if (i["priceChange"] or 0) < 0)
    premiums = [i["premiumPct"] for i in out_items if i["premiumPct"] is not None]
    avg_premium = round(sum(premiums) / len(premiums), 1) if premiums else None

    # 6) 写出 JSON
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "products.json").write_text(
        json.dumps({"updatedAt": now, "items": out_items}, ensure_ascii=False), encoding="utf-8")
    (OUT_DIR / "stats.json").write_text(
        json.dumps({"total": total, "watched": watched_n, "up": up, "down": down,
                    "avgPremium": avg_premium, "updatedAt": now}, ensure_ascii=False), encoding="utf-8")
    (OUT_DIR / "history.json").write_text(json.dumps(history, ensure_ascii=False), encoding="utf-8")
    (OUT_DIR / "alerts.json").write_text(json.dumps({"items": alerts}, ensure_ascii=False), encoding="utf-8")

    print(f"[collect] 完成：商品 {total}，监控 {watched_n}，上涨 {up}，下跌 {down}，平均溢价 {avg_premium}")


if __name__ == "__main__":
    main()
