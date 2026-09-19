# -*- coding: utf-8 -*-
"""SQLite 存储层：商品信息、价格历史、告警、设置。"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

from .config import DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spu_id TEXT UNIQUE NOT NULL,
    title TEXT,
    sub_title TEXT,
    logo_url TEXT,
    article_number TEXT,
    auth_price REAL,
    sell_date TEXT,
    brand TEXT,
    sold_count_text TEXT,
    source TEXT DEFAULT 'manual',
    skus_json TEXT,
    watched INTEGER DEFAULT 0,
    alert_price REAL DEFAULT 0,
    latest_price REAL,
    min_price REAL,
    max_price REAL,
    created_at REAL,
    updated_at REAL
);

CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spu_id TEXT NOT NULL,
    price REAL,
    detail_json TEXT,
    created_at REAL
);
CREATE INDEX IF NOT EXISTS idx_price_history_spu_time
    ON price_history (spu_id, created_at);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spu_id TEXT NOT NULL,
    title TEXT,
    price REAL,
    alert_price REAL,
    channel TEXT,
    sent INTEGER DEFAULT 0,
    message TEXT,
    created_at REAL
);

CREATE TABLE IF NOT EXISTS manual_quotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_number TEXT NOT NULL,
    platform TEXT NOT NULL,
    price REAL,
    sales TEXT,
    link TEXT,
    note TEXT,
    created_at REAL,
    updated_at REAL
);
CREATE INDEX IF NOT EXISTS idx_manual_quotes_article
    ON manual_quotes (article_number);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """兼容旧库的轻量迁移。"""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(products)").fetchall()}
    if "sold_count_text" not in cols:
        conn.execute("ALTER TABLE products ADD COLUMN sold_count_text TEXT")
    if "source" not in cols:
        conn.execute("ALTER TABLE products ADD COLUMN source TEXT DEFAULT 'manual'")


class Database:
    def __init__(self, path: str = str(DB_PATH)):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._conn.executescript(_SCHEMA)
        _migrate(self._conn)
        self._conn.commit()

    # ------------------------------------------------------------------
    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def _query(self, sql: str, params: tuple = ()) -> List[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    # ------------------------------------------------------------------
    def upsert_product(self, info: Dict[str, Any], source: str = "manual") -> int:
        """插入或更新商品基础信息，返回自增 id。"""
        now = time.time()
        existing = self.get_product_by_spu(info["spuId"])
        skus_json = json.dumps(info.get("skus", []), ensure_ascii=False)
        if existing:
            self._execute(
                """UPDATE products SET title=?, sub_title=?, logo_url=?, article_number=?,
                   auth_price=?, sell_date=?, brand=?, sold_count_text=?, skus_json=?, updated_at=?
                   WHERE spu_id=?""",
                (info.get("title"), info.get("subTitle"), info.get("logoUrl"),
                 info.get("articleNumber"), info.get("authPrice"), info.get("sellDate"),
                 info.get("brand"), info.get("soldCountText"), skus_json, now, info["spuId"]),
            )
            return existing["id"]
        cur = self._execute(
            """INSERT INTO products
               (spu_id, title, sub_title, logo_url, article_number, auth_price,
                sell_date, brand, sold_count_text, source, skus_json, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (info["spuId"], info.get("title"), info.get("subTitle"), info.get("logoUrl"),
             info.get("articleNumber"), info.get("authPrice"), info.get("sellDate"),
             info.get("brand"), info.get("soldCountText"), source, skus_json, now, now),
        )
        return cur.lastrowid

    def record_price(self, spu_id: str, price: Optional[float], detail_json: str = "") -> None:
        now = time.time()
        self._execute(
            "INSERT INTO price_history (spu_id, price, detail_json, created_at) VALUES (?,?,?,?)",
            (spu_id, price, detail_json, now),
        )
        row = self.get_product_by_spu(spu_id)
        if row:
            latest = price
            mn = min(row["min_price"], price) if row["min_price"] is not None and price is not None else (price if price is not None else row["min_price"])
            mx = max(row["max_price"], price) if row["max_price"] is not None and price is not None else (price if price is not None else row["max_price"])
            self._execute(
                "UPDATE products SET latest_price=?, min_price=?, max_price=?, updated_at=? WHERE spu_id=?",
                (latest, mn, mx, now, spu_id),
            )

    # ------------------------------------------------------------------
    def get_product_by_spu(self, spu_id: str) -> Optional[sqlite3.Row]:
        rows = self._query("SELECT * FROM products WHERE spu_id=?", (spu_id,))
        return rows[0] if rows else None

    def get_product(self, product_id: int) -> Optional[sqlite3.Row]:
        rows = self._query("SELECT * FROM products WHERE id=?", (product_id,))
        return rows[0] if rows else None

    def list_products(self, watched_only: bool = False, keyword: str = "", source: str = "") -> List[sqlite3.Row]:
        sql = "SELECT * FROM products WHERE 1=1"
        params: list = []
        if watched_only:
            sql += " AND watched=1"
        if keyword:
            sql += " AND (title LIKE ? OR article_number LIKE ?)"
            params += [f"%{keyword}%", f"%{keyword}%"]
        if source:
            sql += " AND source=?"
            params.append(source)
        sql += " ORDER BY updated_at DESC"
        return self._query(sql, tuple(params))

    def set_watch(self, product_id: int, watched: bool, alert_price: float = 0) -> None:
        self._execute(
            "UPDATE products SET watched=?, alert_price=? WHERE id=?",
            (1 if watched else 0, alert_price, product_id),
        )

    def price_history(self, spu_id: str, limit: int = 200) -> List[sqlite3.Row]:
        return self._query(
            "SELECT price, created_at FROM price_history WHERE spu_id=? ORDER BY created_at ASC LIMIT ?",
            (spu_id, limit),
        )

    def watched_products(self) -> List[sqlite3.Row]:
        return self._query("SELECT * FROM products WHERE watched=1")

    # ------------------------------------------------------------------
    # 告警
    # ------------------------------------------------------------------
    def record_alert(self, spu_id: str, title: str, price: float, alert_price: float,
                     channel: str, message: str, sent: bool = False) -> None:
        self._execute(
            """INSERT INTO alerts (spu_id, title, price, alert_price, channel, sent, message, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (spu_id, title, price, alert_price, channel, 1 if sent else 0, message, time.time()),
        )

    def list_alerts(self, limit: int = 100) -> List[sqlite3.Row]:
        return self._query("SELECT * FROM alerts ORDER BY created_at DESC LIMIT ?", (limit,))

    # ------------------------------------------------------------------
    # 设置（key-value，用于通知渠道配置等）
    # ------------------------------------------------------------------
    def get_setting(self, key: str, default: str = "") -> str:
        rows = self._query("SELECT value FROM settings WHERE key=?", (key,))
        return rows[0]["value"] if rows else default

    def set_setting(self, key: str, value: str) -> None:
        self._execute(
            "INSERT INTO settings (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    # ------------------------------------------------------------------
    # 手动报价（覆盖自动抓取不可行的平台：淘宝/京东/拼多多/唯品会）
    # ------------------------------------------------------------------
    def upsert_manual_quote(self, article_number: str, platform: str, price: float,
                            sales: str = "", link: str = "", note: str = "") -> int:
        now = time.time()
        rows = self._query(
            "SELECT id FROM manual_quotes WHERE article_number=? AND platform=?",
            (article_number, platform),
        )
        if rows:
            self._execute(
                "UPDATE manual_quotes SET price=?, sales=?, link=?, note=?, updated_at=? WHERE id=?",
                (price, sales, link, note, now, rows[0]["id"]),
            )
            return rows[0]["id"]
        cur = self._execute(
            """INSERT INTO manual_quotes (article_number, platform, price, sales, link, note, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (article_number, platform, price, sales, link, note, now, now),
        )
        return cur.lastrowid

    def manual_quotes(self, article_number: str) -> List[sqlite3.Row]:
        return self._query(
            "SELECT * FROM manual_quotes WHERE article_number=? ORDER BY updated_at DESC",
            (article_number,),
        )

    def delete_manual_quote(self, quote_id: int) -> None:
        self._execute("DELETE FROM manual_quotes WHERE id=?", (quote_id,))


_db: Optional[Database] = None


def get_db() -> Database:
    global _db
    if _db is None:
        _db = Database()
    return _db
