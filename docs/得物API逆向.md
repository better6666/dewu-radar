# 得物（Dewu/Poizon）App 接口逆向说明

> 本文记录「得物雷达」项目数据抓取层的关键逆向结论，供后续维护参考。
> 逆向依据：公开开源项目（Locusc/dewu-api、ly1205/dewu_stockx、DoubleZ7/dewu-spider-and-analysis）及本地实测验证。

## 一、核心结论

得物 App 接口有两代鉴权机制：

| 代际 | 域名 | 请求体 | 说明 |
|------|------|--------|------|
| v1 老接口 | `app.poizon.com` / `app.dewu.com` | 明文 JSON，带 `sign` | 仅 MD5 签名，简单 |
| v2 新接口 | `app.dewu.com` | `{"data": "<RSA加密的AES密钥>\u200B<AES加密的十六进制>"}` | RSA + AES 加密参数/响应 |

**实测验证结果（2026）**：

| 变体 | 结果 | 含义 |
|------|------|------|
| v1 搜索（`app.poizon.com` + 盐 `19bc…`） | `403 请求已拒绝` | 签名通过，仅 IP 风控拦截 |
| v2 detailV3（web + 盐 `048a…` + web 公钥） | `403 请求已拒绝` | 签名+加密通过，仅 IP 风控拦截 |
| v2 detailV3（web + 盐 `19bc…`） | `401 签名认证失败` | 盐不匹配 |
| v2 detailV3（app 变体） | `400 校验失败:11001` | 需登录 token |

> **重要**：签名与加密算法均已本地验证正确。`403 请求已拒绝` 是得物风控对**数据中心 IP**（本项目测试出口为 AWS `13.231.39.218`）的拦截，并非算法错误。
> 在**家庭/办公网络（住宅 IP）**运行本应用即可拿到真实数据；若部署在云服务器，需配置住宅代理。

## 二、签名算法（sign）

```
sign = md5( 按 key 字母序拼接 "key+value(去除空格)" + 盐 )
```

- 盐有两种：
  - 小程序 / App 接口：`19bc545a393a25177083d4a748807cc0`
  - H5 Web（m.dewu.com）接口：`048a9c4943398714b356a696503d2d36`

```python
import hashlib

def sign(params: dict, salt: str) -> str:
    s = "".join(f"{k}{str(params[k]).replace(' ', '')}" for k in sorted(params)) + salt
    return hashlib.md5(s.encode('utf-8')).hexdigest()
```

## 三、v2 参数加密（RSA + AES）

1. 随机生成 48 位字符串 `origin_key`（字母数字）。
2. AES 密钥 = `origin_key[10:26]`（16 字节），IV = `origin_key[20:36]`（16 字节）。
3. 用 **AES-CBC + PKCS7** 加密参数 JSON，输出**大写十六进制**。
4. 用 **RSA（PKCS1_v1_5，公钥加密）** 加密 `origin_key`，输出 Base64。
5. 请求体：`{"data": "<rsa_base64>\u200B<aes_hex>"}`（中间是零宽空格 `\u200B`）。

响应解密：响应 `data` 字段是十六进制 → Base64 解码 → AES-CBC 解密（密钥/IV 同上）。

### RSA 公钥

- App / 小程序：`MFwwDQYJKoZIhvcNAQEBBQADSwAwSAJBANeBpp2h87T10BskMkdTU4Wlp+9phEqjkSGXttUpBW1s42y0EyHySNfwH7bTEvMN83Dtb40iYxiRFbALdMDgmzsCAwEAAQ==`
- H5 Web：`MFwwDQYJKoZIhvcNAQEBBQADSwAwSAJBANMGZPlLobHYWoZyMvHD0a6emIjEmtf5Z6Q++VIBRulxsUfYvcczjB0fMVvAnd1douKmOX4G690q9NZ6Q7z/TV8CAwEAAQ==`
- 搜索：`MFwwDQYJKoZIhvcNAQEBBQADSwAwSAJBANSuWgzWxJ1a26/6c3nrCQP68acn9tyQr6rD02HmLKhnge9yg65nNvYdtcWAKWPu27ibIL3bvqdmJUUWKD3VG10CAwEAAQ==`

## 四、关键接口

| 用途 | 接口路径 | 参数 | 盐/公钥 |
|------|----------|------|---------|
| 搜索 | `/api/v1/h5/search/fire/search/list` | `title,page,sortType,sortMode,limit,showHot,isAggr` | 盐 `19bc…` |
| 首页推荐流 | `/api/v1/h5/index/fire/index`（`app.poizon.com`，POST） | `tabId,limit,lastId` | 盐 `19bc…` |
| 商品详情 | `/api/v1/h5/index/fire/flow/product/detailV3` | `spuId,productSourceName,propertyValueId,sourceName=shareDetail` | 盐 `048a…`，web 公钥 |
| SKU 价格 | `/api/v1/h5/inventory/price/h5/queryBuyNowInfo` | `spuId` | 盐 `048a…`，web 公钥 |
| 最近成交 | `/api/v1/h5/commodity/fire/last-sold-list` | `spuId,limit,lastId,sourceApp` | 盐 `19bc…`，app 公钥 |

> ⭐ **首页推荐流（`index/fire/index`）风控较宽松**：实测即使从数据中心 IP 请求也返回 HTTP 200 真实数据，可用于**批量采集热门商品**（每页 16–18 个，`lastId` 翻页，`tabId` 切换内容流）。响应结构 `data.hotList[].product`，含 `spuId/title/subTitle/price(分)/authPrice(分)/logoUrl/articleNumber/sellDate/soldCountText` 等字段。这是本应用「一键采集热门」功能的数据来源。

## 五、关键请求头

- 通用：`Host: app.dewu.com`、`appVersion: 4.4.0`、`platform: h5`、`Accept-Encoding: gzip, deflate, br`
- Web 变体：`AppId: h5`、`Origin/Referer: https://m.dewu.com`、`sks: 1,hdw3`
- 小程序变体：`AppId: wxapp`、`Referer: https://servicewechat.com/...`、`sks: 1,xdw1`（需 `SK`/`Wxapp-Login-Token`/`X-Auth-Token`，需登录）

## 六、字段说明（商品详情 `data` 结构）

- `detail`：`title`（标题）、`subTitle`、`logoUrl`（主图）、`authPrice`（发售价）、`sellDate`（发售日期）、`articleNumber`（货号）、`spuId`
- `baseProperties.list`：品牌、系列等参数；`baseProperties.brandList`：品牌
- `skus`：各 SKU（尺码）及 `skuId`、`properties`
- `saleProperties.list`：尺码属性（`propertyValueId` ↔ 尺码值）
- `imageAndText`：详情图文

## 七、风险控制提示

- 得物风控（数美/同盾类）会拦截数据中心 IP，返回 `403 请求已拒绝`。
- 应对：住宅 IP 直接访问；云服务器部署需配置住宅代理；控制请求频率（间隔 1–3 秒）。
- 若返回 `请校验验证码`，表示触发滑块验证，需降低频率或切换 IP。
