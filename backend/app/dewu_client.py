# -*- coding: utf-8 -*-
"""得物（Dewu）数据抓取客户端。

实现得物 App 接口的签名（MD5）与 RSA+AES 参数/响应加解密，
提供搜索、商品详情、SKU 价格、最近成交等数据抓取能力。

算法与公钥依据见 docs/得物API逆向.md。
"""
from __future__ import annotations

import base64
import hashlib
import json
import random
import re
import ssl
import time
from typing import Any, Dict, Optional

import requests
from Crypto.Cipher import AES, PKCS1_v1_5
from Crypto.PublicKey import RSA

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
SALT_WXAPP = "19bc545a393a25177083d4a748807cc0"   # 小程序 / App 接口盐
SALT_WEB = "048a9c4943398714b356a696503d2d36"     # H5 Web 接口盐

PUBLIC_KEY_APP = """-----BEGIN PUBLIC KEY-----
MFwwDQYJKoZIhvcNAQEBBQADSwAwSAJBANeBpp2h87T10BskMkdTU4Wlp+9phEqjkSGXttUpBW1s42y0EyHySNfwH7bTEvMN83Dtb40iYxiRFbALdMDgmzsCAwEAAQ==
-----END PUBLIC KEY-----"""
PUBLIC_KEY_WEB = """-----BEGIN PUBLIC KEY-----
MFwwDQYJKoZIhvcNAQEBBQADSwAwSAJBANMGZPlLobHYWoZyMvHD0a6emIjEmtf5Z6Q++VIBRulxsUfYvcczjB0fMVvAnd1douKmOX4G690q9NZ6Q7z/TV8CAwEAAQ==
-----END PUBLIC KEY-----"""
PUBLIC_KEY_SEARCH = """-----BEGIN PUBLIC KEY-----
MFwwDQYJKoZIhvcNAQEBBQADSwAwSAJBANSuWgzWxJ1a26/6c3nrCQP68acn9tyQr6rD02HmLKhnge9yg65nNvYdtcWAKWPu27ibIL3bvqdmJUUWKD3VG10CAwEAAQ==
-----END PUBLIC KEY-----"""

BASE_URL = "https://app.dewu.com"

UA_WXAPP = (
    "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/53.0.2785.143 Safari/537.36 MicroMessenger/7.0.9.501 NetType/WIFI "
    "MiniProgramEnv/Windows WindowsWechat"
)
UA_WEB = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/13.0.3 Mobile/15E148 Safari/604.1"
)

_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

# 风控 / 业务错误提示
MSG_VERIFY_CAPTCHA = "请校验验证码"
MSG_REJECTED = "请求已拒绝"


class DewuError(Exception):
    """得物接口业务错误。"""

    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


def sign(params: Dict[str, Any], salt: str) -> str:
    """计算得物签名：按 key 字母序拼接 key+value(去空格) + 盐，再 MD5。"""
    s = "".join(f"{k}{str(params[k]).replace(' ', '')}" for k in sorted(params)) + salt
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def _rand_key(n: int = 48) -> str:
    return "".join(random.choice(_CHARS) for _ in range(n))


def _rsa_encrypt(message: str, public_key: str) -> str:
    cipher = PKCS1_v1_5.new(RSA.import_key(public_key))
    return base64.b64encode(cipher.encrypt(message.encode("utf-8"))).decode()


def _aes_encrypt_hex(plaintext: str, key: str, iv: str) -> str:
    pad = 16 - len(plaintext.encode("utf-8")) % 16
    data = plaintext.encode("utf-8") + bytes([pad]) * pad
    cipher = AES.new(key.encode("utf-8"), AES.MODE_CBC, iv.encode("utf-8"))
    return "".join(f"{b:02X}" for b in cipher.encrypt(data))


def _aes_decrypt(hexdata: str, key: str, iv: str) -> str:
    raw = bytes.fromhex(hexdata)
    cipher = AES.new(key.encode("utf-8"), AES.MODE_CBC, iv.encode("utf-8"))
    plain = cipher.decrypt(raw)
    pad = plain[-1]
    return plain[:-pad].decode("utf-8", "replace")


def _encrypt_params(src: str, public_key: str):
    """加密请求参数，返回 (请求体 dict, origin_key)。"""
    origin = _rand_key()
    aes_key, iv = origin[10:26], origin[20:36]
    enc_key = _rsa_encrypt(origin, public_key)
    enc_body = _aes_encrypt_hex(src, aes_key, iv)
    # \u200B 为零宽空格，得物要求作为分隔符
    return {"data": enc_key + "\u200B" + enc_body}, origin


def _decrypt_response(encrypt_data: str, origin: str) -> str:
    key, iv = origin[10:26], origin[20:36]
    return _aes_decrypt(encrypt_data, key, iv)


class DewuClient:
    """得物数据客户端。

    proxy: 可选 HTTP 代理，如 "http://user:pass@host:port"（部署在云服务器时用住宅代理）。
    timeout: 单次请求超时（秒）。
    """

    def __init__(self, proxy: Optional[str] = None, timeout: int = 15):
        self.session = requests.Session()
        self.proxy = proxy
        self.timeout = timeout
        self._verify = True
        try:
            # 某些环境下系统 CA 不全，尝试导入 certifi；失败则跳过校验
            import certifi  # noqa: F401
        except ImportError:
            self._verify = False

    # ------------------------------------------------------------------
    # 底层请求
    # ------------------------------------------------------------------
    def _proxies(self):
        return {"http": self.proxy, "https": self.proxy} if self.proxy else None

    def _get(self, url: str, headers: Dict[str, str]) -> str:
        r = self.session.get(url, headers=headers, proxies=self._proxies(),
                             timeout=self.timeout, verify=self._verify)
        return r.text

    def _post_json(self, url: str, data: Dict[str, Any], headers: Dict[str, str]) -> str:
        r = self.session.post(url, json=data, headers=headers, proxies=self._proxies(),
                              timeout=self.timeout, verify=self._verify)
        return r.text

    def _check(self, text: str, origin: Optional[str] = None) -> str:
        """解析响应：若为明文 JSON 则直接返回；若为加密 data 则解密。"""
        if MSG_VERIFY_CAPTCHA in text:
            raise DewuError(403, "触发滑块验证码，请降低频率或更换 IP")
        if MSG_REJECTED in text:
            raise DewuError(403, "请求被得物风控拒绝（常见于数据中心 IP，需住宅 IP / 代理）")
        try:
            j = json.loads(text)
        except json.JSONDecodeError:
            return text
        if isinstance(j, dict) and j.get("code") not in (None, 200) and j.get("error"):
            raise DewuError(int(j.get("code", -1)), j.get("msg", text[:200]))
        if isinstance(j, dict) and isinstance(j.get("data"), str) and origin:
            return _decrypt_response(j["data"], origin)
        return text

    # ------------------------------------------------------------------
    # 搜索
    # ------------------------------------------------------------------
    def search(self, keyword: str, page: int = 0, limit: int = 20) -> Dict[str, Any]:
        """关键词搜索商品列表。

        使用 app.poizon.com 老接口 + 明文 sign（实测可通过签名校验）。
        """
        from urllib.parse import urlencode

        params = {
            "title": keyword, "page": page, "sortType": 1, "sortMode": 1,
            "limit": limit, "showHot": -1, "unionId": "",
        }
        qs = urlencode({"sign": sign(params, SALT_WXAPP), **params})
        url = f"https://app.poizon.com/api/v1/h5/search/fire/search/list?{qs}"
        headers = {
            "Host": "app.poizon.com",
            "User-Agent": UA_WXAPP,
            "appid": "wxapp",
            "appversion": "4.4.0",
            "Accept": "*/*",
        }
        text = self._get(url, headers)
        return json.loads(self._check(text))

    # ------------------------------------------------------------------
    # 首页推荐流（批量采集热门商品，无需登录、风控较宽松）
    # ------------------------------------------------------------------
    def discover(self, last_id: int = 1, limit: int = 20, tab_id: str = "") -> Dict[str, Any]:
        """抓取得物首页推荐流，返回热门商品列表（可翻页）。"""
        params = {"tabId": tab_id, "limit": limit, "lastId": last_id}
        params["sign"] = sign(params, SALT_WXAPP)
        url = f"{BASE_URL}/api/v1/h5/index/fire/index"
        # 首页流走 app.poizon.com 老接口
        url = url.replace("app.dewu.com", "app.poizon.com")
        headers = {
            "Host": "app.poizon.com",
            "User-Agent": UA_WXAPP,
            "appid": "wxapp",
            "appversion": "4.4.0",
            "content-type": "application/json",
            "Accept": "*/*",
        }
        text = self._post_json(url, params, headers)
        return json.loads(self._check(text))

    # ------------------------------------------------------------------
    # 商品详情（v2 加密）
    # ------------------------------------------------------------------
    def product_detail(self, spu_id: str) -> Dict[str, Any]:
        """获取商品详情（detailV3，Web 变体，无需登录）。"""
        params = {
            "spuId": str(spu_id), "productSourceName": "", "propertyValueId": "",
            "sourceName": "shareDetail",
        }
        params["sign"] = sign(params, SALT_WEB)
        post_data, origin = _encrypt_params(json.dumps(params), PUBLIC_KEY_WEB)
        url = f"{BASE_URL}/api/v1/h5/index/fire/flow/product/detailV3"
        headers = self._web_headers()
        text = self._post_json(url, post_data, headers)
        return json.loads(self._check(text, origin))

    # ------------------------------------------------------------------
    # SKU 价格列表
    # ------------------------------------------------------------------
    def sku_price_list(self, spu_id: str) -> Dict[str, Any]:
        """获取商品各尺码（SKU）价格。"""
        params = {"spuId": str(spu_id)}
        params["sign"] = sign(params, SALT_WEB)
        post_data, origin = _encrypt_params(json.dumps(params), PUBLIC_KEY_WEB)
        url = f"{BASE_URL}/api/v1/h5/inventory/price/h5/queryBuyNowInfo"
        headers = self._web_headers()
        text = self._post_json(url, post_data, headers)
        return json.loads(self._check(text, origin))

    # ------------------------------------------------------------------
    # 最近成交（App 变体，可能需要登录，尽力而为）
    # ------------------------------------------------------------------
    def last_sold(self, spu_id: str, limit: int = 20, last_id: str = "") -> Dict[str, Any]:
        """获取最近成交记录。"""
        params = {"spuId": str(spu_id), "limit": limit, "lastId": last_id, "sourceApp": "app"}
        params["sign"] = sign(params, SALT_WXAPP)
        post_data, origin = _encrypt_params(json.dumps(params), PUBLIC_KEY_APP)
        url = f"{BASE_URL}/api/v1/h5/commodity/fire/last-sold-list"
        headers = self._wxapp_headers()
        text = self._post_json(url, post_data, headers)
        return json.loads(self._check(text, origin))

    # ------------------------------------------------------------------
    # 便捷方法：抓取完整行情（详情 + 各尺码价格）
    # ------------------------------------------------------------------
    def fetch_product(self, spu_id: str) -> Dict[str, Any]:
        """抓取商品详情与 SKU 价格，合并为统一结构。"""
        detail = self.product_detail(spu_id)
        price_data = None
        try:
            price_data = self.sku_price_list(spu_id)
        except DewuError:
            price_data = None
        return {"detail": detail, "prices": price_data}

    # ------------------------------------------------------------------
    # 请求头
    # ------------------------------------------------------------------
    def _base_headers(self) -> Dict[str, str]:
        return {
            "Host": "app.dewu.com",
            "appVersion": "4.4.0",
            "platform": "h5",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }

    def _web_headers(self) -> Dict[str, str]:
        h = self._base_headers()
        h.update({
            "AppId": "h5",
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh,zh-CN;q=0.9",
            "Origin": "https://m.dewu.com",
            "Referer": "https://m.dewu.com/",
            "sks": "1,hdw3",
            "User-Agent": UA_WEB,
        })
        return h

    def _wxapp_headers(self) -> Dict[str, str]:
        h = self._base_headers()
        h.update({
            "AppId": "wxapp",
            "Content-Type": "application/json",
            "User-Agent": UA_WXAPP,
            "sks": "1,xdw1",
            "Referer": "https://servicewechat.com/wx3c12cdd0ae8b1a7b/271/page-frame.html",
        })
        return h


# ---------------------------------------------------------------------------
# 数据解析辅助（把得物原始响应转成统一字段，便于入库 / 前端展示）
# ---------------------------------------------------------------------------
def parse_detail(detail_json: Dict[str, Any]) -> Dict[str, Any]:
    """从商品详情响应中提取关键字段。"""
    data = detail_json.get("data") or {}
    d = data.get("detail") or {}
    brand = ""
    brand_list = (data.get("baseProperties") or {}).get("brandList") or []
    if brand_list:
        brand = brand_list[0].get("brandName") or ""

    # 尺码属性映射 propertyValueId -> 尺码
    size_map = {}
    sale_props = (data.get("saleProperties") or {}).get("list") or []
    for prop in sale_props:
        if prop.get("name") == "尺码":
            size_map[prop.get("propertyValueId")] = prop.get("value")

    skus = data.get("skus") or []
    return {
        "spuId": d.get("spuId"),
        "title": d.get("title"),
        "subTitle": d.get("subTitle"),
        "logoUrl": d.get("logoUrl"),
        "articleNumber": d.get("articleNumber"),      # 货号
        "authPrice": _yuan(d.get("authPrice")),        # 发售价
        "sellDate": d.get("sellDate"),
        "brand": brand,
        "skus": [
            {
                "skuId": s.get("skuId"),
                "size": next((size_map.get(p.get("propertyValueId"))
                              for p in (s.get("properties") or [])
                              if p.get("propertyValueId") in size_map), None),
            }
            for s in skus
        ],
    }


def parse_prices(prices_json: Optional[Dict[str, Any]]) -> list:
    """从 SKU 价格响应中提取各尺码价格。"""
    if not prices_json:
        return []
    data = prices_json.get("data") or {}
    out = []
    for info in data.get("skuInfoList") or []:
        item = {"skuId": info.get("skuId")}
        for ch in info.get("tradeChannelInfoList") or []:
            desc = ch.get("tradeDesc") or "价格"
            price = ch.get("finalPrice") or ch.get("price")
            if price is not None:
                item[desc] = _yuan(price)
        out.append(item)
    return out


def merge_skus(skus: list, prices: list) -> list:
    """把尺码信息与各尺码价格合并（按 skuId）。"""
    price_by_id = {p.get("skuId"): p for p in prices if p.get("skuId")}
    merged = []
    for s in skus:
        m = dict(s)
        m.update(price_by_id.get(s.get("skuId"), {}))
        merged.append(m)
    return merged


def parse_discover(discover_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从首页推荐流响应中提取标准化商品列表。"""
    data = discover_json.get("data") or {}
    out = []
    for h in data.get("hotList") or []:
        p = h.get("product") or {}
        if not p.get("spuId"):
            continue
        out.append({
            "spuId": str(p["spuId"]),
            "title": p.get("title"),
            "subTitle": p.get("subTitle"),
            "logoUrl": p.get("logoUrl"),
            "articleNumber": p.get("articleNumber"),
            "authPrice": _yuan(p.get("authPrice")),
            "price": _yuan(p.get("price")),          # 当前价
            "sellDate": p.get("sellDate"),
            "soldCountText": p.get("soldCountText"),  # 销量文本，如「已售1.2万」
            "brand": None,
            "skus": [],
        })
    return out


def _yuan(price: Any) -> Optional[float]:
    """得物价格单位是「分」，转换为「元」。"""
    if price is None:
        return None
    try:
        return round(float(price) / 100.0, 2)
    except (TypeError, ValueError):
        return None
