# -*- coding: utf-8 -*-
"""应用配置。"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent          # backend/
DATA_DIR = Path(os.environ.get("DEWU_DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "dewu.db"

# 得物抓取相关
DEWU_PROXY = os.environ.get("DEWU_PROXY", "") or None       # 住宅代理，如 http://user:pass@host:port
DEWU_TIMEOUT = int(os.environ.get("DEWU_TIMEOUT", "15"))

# 监控轮询间隔（秒）
POLL_INTERVAL = int(os.environ.get("DEWU_POLL_INTERVAL", "600"))

# 单个商品最低价格告警阈值（元），0 表示不告警
DEFAULT_ALERT_PRICE = float(os.environ.get("DEWU_ALERT_PRICE", "0"))
