# -*- coding: utf-8 -*-
"""价格告警推送通知，支持多种渠道。

渠道通过 settings 表中的 `notify_config`（JSON）配置：
{
  "channel": "bark" | "serverchan" | "dingtalk" | "webhook",
  "bark_url": "https://api.day.app/你的key",
  "serverchan_key": "SCT...",
  "dingtalk_webhook": "https://oapi.dingtalk.com/robot/send?access_token=...",
  "webhook_url": "https://example.com/hook",
  "enabled": true
}
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger("dewu.notify")


class Notifier:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

    # ------------------------------------------------------------------
    def send(self, title: str, body: str) -> Dict[str, Any]:
        """按配置的渠道发送通知，返回结果。"""
        if not self.config.get("enabled", False):
            return {"ok": False, "error": "通知未启用"}
        channel = self.config.get("channel", "")
        try:
            if channel == "bark":
                return self._send_bark(title, body)
            if channel == "serverchan":
                return self._send_serverchan(title, body)
            if channel == "dingtalk":
                return self._send_dingtalk(title, body)
            if channel == "webhook":
                return self._send_webhook(title, body)
            return {"ok": False, "error": f"未知渠道 {channel}"}
        except Exception as e:  # noqa: BLE001
            logger.exception("通知发送失败")
            return {"ok": False, "error": repr(e)}

    # ------------------------------------------------------------------
    def _send_bark(self, title: str, body: str) -> Dict[str, Any]:
        base = (self.config.get("bark_url") or "").rstrip("/")
        if not base:
            return {"ok": False, "error": "未配置 bark_url"}
        r = requests.post(f"{base}/{title}/{body}", timeout=10)
        return {"ok": r.status_code == 200, "status": r.status_code}

    def _send_serverchan(self, title: str, body: str) -> Dict[str, Any]:
        key = self.config.get("serverchan_key") or ""
        if not key:
            return {"ok": False, "error": "未配置 serverchan_key"}
        r = requests.post(
            f"https://sctapi.ftqq.com/{key}.send",
            data={"title": title, "desp": body}, timeout=10,
        )
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        return {"ok": data.get("code") == 0 or r.status_code == 200, "status": r.status_code}

    def _send_dingtalk(self, title: str, body: str) -> Dict[str, Any]:
        webhook = self.config.get("dingtalk_webhook") or ""
        if not webhook:
            return {"ok": False, "error": "未配置 dingtalk_webhook"}
        r = requests.post(
            webhook,
            json={"msgtype": "markdown", "markdown": {"title": title, "text": f"### {title}\n\n{body}"}},
            timeout=10,
        )
        data = r.json()
        return {"ok": data.get("errcode") == 0, "status": r.status_code}

    def _send_webhook(self, title: str, body: str) -> Dict[str, Any]:
        url = self.config.get("webhook_url") or ""
        if not url:
            return {"ok": False, "error": "未配置 webhook_url"}
        r = requests.post(url, json={"title": title, "body": body}, timeout=10)
        return {"ok": r.status_code in (200, 204), "status": r.status_code}


def load_config(db) -> Dict[str, Any]:
    """从 settings 表读取通知配置。"""
    raw = db.get_setting("notify_config", "{}")
    try:
        return json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return {}


def build_alert_message(product: Dict[str, Any], price: float, alert_price: float) -> tuple[str, str]:
    """构造告警通知的标题与正文。"""
    title = f"📉 {product.get('title') or product.get('spu_id')} 价格跌破阈值"
    body = (
        f"**商品**：{product.get('title') or '—'}\n"
        f"**货号**：{product.get('article_number') or '—'}\n"
        f"**当前价**：¥{price:.2f}\n"
        f"**告警价**：¥{alert_price:.2f}\n"
        f"**降幅**：¥{alert_price - price:.2f}\n"
    )
    return title, body
