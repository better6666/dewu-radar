# 得物雷达 · Dewu Radar

一个前后端分离的 Web 应用，用于监控**得物（Dewu/Poizon）**商品的行情：抓取真实价格、销量、各尺码报价，记录价格历史并展示走势。

## 功能

- ⚡ **一键采集热门**：从得物首页推荐流批量抓取热门商品（无需手动搜货号），一键填充行情库
- 🔍 **搜索**：按鞋款名 / 货号搜索得物商品
- 📊 **行情抓取**：抓取商品详情（标题、品牌、发售价、货号、图片）与各尺码报价
- 👁 **监控**：将商品加入监控列表，后端定时轮询价格
- 📈 **价格走势**：ECharts 展示历史价格曲线、涨跌幅、溢价率、最高/最低价
- 📊 **涨跌榜**：按涨幅 / 跌幅 / 溢价 / 价格排序
- 🔔 **推送通知**：价格跌破告警价时自动推送（支持 Bark / Server酱 / 钉钉 / 自定义 Webhook）
- 🚨 **告警记录**：记录所有价格告警及其推送状态

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.10+ / FastAPI / SQLite / pycryptodome |
| 前端 | React 18 / Vite 5 / ECharts 5 |

## 目录结构

```
得物雷达/
├── backend/            # FastAPI 后端
│   ├── app/
│   │   ├── main.py         # REST API
│   │   ├── dewu_client.py  # 得物抓取客户端（签名 + RSA/AES 加解密）
│   │   ├── db.py           # SQLite 存储
│   │   ├── scheduler.py    # 定时监控调度
│   │   └── config.py       # 配置
│   └── requirements.txt
├── frontend/           # React 前端
│   └── src/
├── docs/得物API逆向.md   # 得物接口逆向说明
└── README.md
```

## 快速开始

### 1. 后端

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload
```

### 2. 前端

```bash
cd frontend
npm install
npm run dev                      # 默认 http://localhost:5173
```

打开 http://localhost:5173 ，即可搜索、抓取、监控。

> 前端 dev 服务器已配置代理，将 `/api` 转发到后端 `http://127.0.0.1:8010`。

## ⚠️ 重要：关于数据抓取与 IP 风控

得物接口有较强的**风控**，会拦截**数据中心 IP**（云服务器、代理机房等），返回 `403 请求已拒绝`。

- ✅ **在本机（家庭/办公网络，住宅 IP）直接运行**：通常可正常抓取真实数据。
- ❌ 部署在云服务器（AWS/阿里云等）时，需配置**住宅代理**：

  ```bash
  export DEWU_PROXY="http://user:pass@proxy-host:port"
  ```

  后端会通过该代理发起抓取请求。

- 若返回「请校验验证码」，表示触发滑块，应**降低轮询频率**或**更换 IP**。

签名算法与加解密逻辑已在本项目内完成自检（MD5 签名、RSA+AES 往返加解密均验证通过）；在数据中心 IP 下仅会被风控拦截，属预期行为。

## 环境变量（后端）

| 变量 | 默认 | 说明 |
|------|------|------|
| `DEWU_PROXY` | 空 | HTTP 住宅代理地址 |
| `DEWU_TIMEOUT` | 15 | 抓取请求超时（秒） |
| `DEWU_POLL_INTERVAL` | 600 | 监控轮询间隔（秒） |
| `DEWU_DATA_DIR` | `backend/data` | SQLite 数据目录 |
| `DEWU_ALERT_PRICE` | 0 | 默认告警价 |

## API 概览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/search?q=` | 搜索商品 |
| POST | `/api/collect` | 批量采集首页热门商品（`pages`/`limit`） |
| POST | `/api/products/fetch` | 抓取并入库单个商品（`spuId` 或 `keyword`） |
| GET | `/api/stats` | 仪表盘统计指标 |
| GET | `/api/products` | 商品列表（`watched`/`q` 过滤，含涨跌/趋势/溢价） |
| GET | `/api/products/{id}` | 商品详情 + 价格历史 |
| POST | `/api/products/{id}/watch` | 加入/取消监控、设告警价 |
| GET | `/api/products/{id}/history` | 价格历史 |
| POST | `/api/poll` | 手动触发一次监控轮询（含告警检测） |
| GET/POST | `/api/settings` | 读取/保存通知配置 |
| POST | `/api/notify/test` | 发送测试通知 |
| GET | `/api/alerts` | 告警记录列表 |

## 推送通知配置

在界面「🔔 推送设置」中选择渠道并填写配置：

| 渠道 | 需填写 | 说明 |
|------|--------|------|
| Bark | `bark_url` | iOS 推送，App Store 装 Bark 后复制你的推送地址 |
| Server酱 | `serverchan_key` | 微信推送，sct.ftqq.com 获取 SendKey |
| 钉钉机器人 | `dingtalk_webhook` | 钉钉群自定义机器人 Webhook |
| 自定义 Webhook | `webhook_url` | 任意接收 JSON `{title, body}` 的 HTTP 地址 |

保存后点击「发送测试」验证；给监控商品设置告警价，价格跌破即自动推送。

## 免责声明

本项目仅供学习与技术研究，请遵守得物平台的服务条款与相关法律法规，合理控制抓取频率，勿用于商业用途。
