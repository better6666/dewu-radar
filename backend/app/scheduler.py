# -*- coding: utf-8 -*-
"""后台定时监控调度：周期性抓取监控中的商品价格。"""
from __future__ import annotations

import json
import threading
import time
import logging

from .config import POLL_INTERVAL, DEWU_PROXY, DEWU_TIMEOUT
from .db import get_db
from .dewu_client import DewuClient, DewuError, merge_skus, parse_detail, parse_prices
from .notify import Notifier, build_alert_message, load_config

logger = logging.getLogger("dewu.scheduler")


class Scheduler:
    def __init__(self):
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._client = DewuClient(proxy=DEWU_PROXY, timeout=DEWU_TIMEOUT)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="dewu-poll", daemon=True)
        self._thread.start()
        logger.info("监控调度已启动，轮询间隔 %s 秒", POLL_INTERVAL)

    def stop(self) -> None:
        self._stop.set()

    def poll_once(self) -> dict:
        """手动触发一次全量轮询，返回统计信息。"""
        db = get_db()
        products = db.watched_products()
        ok = fail = 0
        errors = []
        for p in products:
            try:
                self._poll_one(p)
                ok += 1
            except DewuError as e:
                fail += 1
                errors.append({"spuId": p["spu_id"], "error": str(e)})
            except Exception as e:  # noqa: BLE001
                fail += 1
                errors.append({"spuId": p["spu_id"], "error": repr(e)})
            time.sleep(2)  # 控制频率，降低风控
        return {"total": len(products), "ok": ok, "fail": fail, "errors": errors}

    def _poll_one(self, p) -> None:
        db = get_db()
        result = self._client.fetch_product(p["spu_id"])
        detail = result["detail"]
        info = parse_detail(detail)
        prices = parse_prices(result["prices"])
        info["skus"] = merge_skus(info["skus"], prices)
        db.upsert_product(info)

        if prices:
            # 取所有尺码中的最低价作为参考价
            min_price = None
            for sku in prices:
                vals = [v for k, v in sku.items() if isinstance(v, (int, float))]
                if vals:
                    sku_min = min(vals)
                    min_price = sku_min if min_price is None else min(min_price, sku_min)
        else:
            min_price = None

        detail_json = json.dumps({"detail": detail, "prices": result["prices"]},
                                 ensure_ascii=False, default=str)
        db.record_price(p["spu_id"], min_price, detail_json)

        # 告警检测：价格跌破阈值时推送通知
        self._check_alert(p, min_price)

    def _check_alert(self, p, price) -> None:
        """价格低于告警价时触发通知。"""
        if price is None or not p["alert_price"] or price >= p["alert_price"]:
            return
        db = get_db()
        cfg = load_config(db)
        if not cfg.get("enabled"):
            db.record_alert(p["spu_id"], p["title"], price, p["alert_price"],
                            cfg.get("channel", ""), "告警（通知未启用）", sent=False)
            return
        title, body = build_alert_message(dict(p), price, p["alert_price"])
        res = Notifier(cfg).send(title, body)
        db.record_alert(p["spu_id"], p["title"], price, p["alert_price"],
                        cfg.get("channel", ""), body, sent=bool(res.get("ok")))
        logger.info("告警推送 spuId=%s price=%s result=%s", p["spu_id"], price, res)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll_once()
            except Exception:  # noqa: BLE001
                logger.exception("轮询失败")
            self._stop.wait(POLL_INTERVAL)


_scheduler: Scheduler | None = None


def get_scheduler() -> Scheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = Scheduler()
    return _scheduler
