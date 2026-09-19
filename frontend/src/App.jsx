import React, { useEffect, useMemo, useState } from 'react'
import { api, IS_DEV } from './api'
import PriceChart from './PriceChart'

const IS_STATIC = !IS_DEV

// ---------------------------------------------------------------------------
// 工具
// ---------------------------------------------------------------------------
const fmt = (v) => (v == null ? '—' : '¥' + Number(v).toFixed(2))
const fmtPct = (v) => (v == null || v === 0 ? '0.00%' : (v > 0 ? '+' : '') + Number(v).toFixed(2) + '%')
const upOf = (v) => (v == null ? 0 : v) > 0

const CHANNELS = [
  { key: '普通发货', label: '普通发货', desc: '平台标准发货', color: '#4f8cff' },
  { key: '闪电直发', label: '闪电直发', desc: '现货秒发', color: '#8b5cf6' },
  { key: '极速发货', label: '极速发货', desc: '最快时效', color: '#06b6d4' },
  { key: '香港直邮', label: '香港直邮', desc: '跨境直邮', color: '#f59e0b' },
]

function channelMin(skus, key) {
  const vals = (skus || []).map((s) => s[key]).filter((v) => v != null)
  return vals.length ? Math.min(...vals) : null
}

// ---------------------------------------------------------------------------
// 迷你趋势图
// ---------------------------------------------------------------------------
function Sparkline({ data, trend }) {
  if (!data || data.length < 2) return <span className="spark-empty">暂无走势</span>
  const w = 116, h = 34, pad = 2
  const min = Math.min(...data), max = Math.max(...data)
  const range = max - min || 1
  const pts = data.map((v, i) => [ (i / (data.length - 1)) * w, h - pad - ((v - min) / range) * (h - pad * 2) ])
  const line = pts.map((p, i) => (i === 0 ? `M${p[0]},${p[1]}` : `L${p[0]},${p[1]}`)).join(' ')
  const area = `${line} L${pts[pts.length - 1][0]},${h} L${pts[0][0]},${h} Z`
  const c = trend > 0 ? 'var(--up)' : trend < 0 ? 'var(--down)' : 'var(--muted)'
  const gid = trend > 0 ? 'gup' : 'gdown'
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="spark">
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={c} stopOpacity="0.28" />
          <stop offset="100%" stopColor={c} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${gid})`} />
      <path d={line} fill="none" stroke={c} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function StatCard({ label, value, sub, tone }) {
  return (
    <div className={`stat-card ${tone || ''}`}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value ?? '—'}</div>
      {sub != null && <div className="stat-sub">{sub}</div>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// 商品卡片
// ---------------------------------------------------------------------------
function ProductCard({ p, onOpen, onToggleWatch }) {
  const change = p.priceChange || 0
  const pct = p.priceChangePct || 0
  const trend = change > 0 ? 1 : change < 0 ? -1 : 0
  const isStored = p.id != null
  const price = p.latestPrice ?? p.price ?? p.authPrice
  return (
    <div className="pcard" onClick={() => onOpen(p)}>
      <div className="pcard-img">
        {p.logoUrl ? <img src={p.logoUrl} alt={p.title} loading="lazy" /> : <div className="noimg">无图</div>}
        {p.brand && <span className="brand-badge">{p.brand}</span>}
        {p.watched ? <span className="watched-badge">● 监控</span> : null}
      </div>
      <div className="pcard-body">
        <div className="pcard-title" title={p.title}>{p.title || '—'}</div>
        <div className="pcard-code">{p.articleNumber || p.subTitle || p.soldCountText || ' '}</div>
        <div className="pcard-price-row">
          <span className="pcard-price">{fmt(price)}</span>
          {isStored ? (
            <span className={`delta ${trend > 0 ? 'up' : trend < 0 ? 'down' : ''}`}>
              {trend > 0 ? '▲' : trend < 0 ? '▼' : '—'} {fmtPct(pct)}
            </span>
          ) : (
            <span className="delta">去抓取 →</span>
          )}
        </div>
        {isStored ? <Sparkline data={p.sparkline} trend={trend} /> : <span className="spark-empty">点击查看实时行情</span>}
        <div className="pcard-foot">
          <span className="auth">{isStored ? `发售价 ${fmt(p.authPrice)}` : (p.soldNum ? `销量 ${p.soldNum}` : ' ')}</span>
          {!IS_STATIC && (
            <button className={`watch-pill ${p.watched ? 'on' : ''}`} onClick={(e) => { e.stopPropagation(); onToggleWatch(p) }}>
              {p.watched ? '监控中' : '+ 监控'}
            </button>
          )}
          {IS_STATIC && p.watched ? <span className="watch-pill on">监控中</span> : null}
        </div>
      </div>
    </div>
  )
}

function Skeleton({ n = 8 }) {
  return <div className="grid">{Array.from({ length: n }).map((_, i) => <div key={i} className="pcard skel" />)}</div>
}

// ---------------------------------------------------------------------------
// 排行榜
// ---------------------------------------------------------------------------
function RankRow({ item, idx, metric, tone, onOpen }) {
  return (
    <div className="rank-row" onClick={() => onOpen(item)}>
      <span className={`rank-no ${idx < 3 ? 'top' : ''}`}>{idx + 1}</span>
      {item.logoUrl ? <img className="rank-img" src={item.logoUrl} alt="" loading="lazy" /> : <span className="rank-img noimg" />}
      <div className="rank-info">
        <div className="rank-title" title={item.title}>{item.title || '—'}</div>
        <div className="rank-price">{fmt(item.latestPrice)}</div>
      </div>
      <span className={`rank-metric ${tone || ''}`}>{metric(item)}</span>
    </div>
  )
}

function RankColumn({ title, note, items, metric, tone, onOpen }) {
  return (
    <div className="rank-col">
      <div className="rank-col-head">
        <span className="rank-col-title">{title}</span>
        <span className="rank-col-note">{note}</span>
      </div>
      {items.length === 0 ? (
        <div className="empty small">暂无数据</div>
      ) : (
        items.map((it, i) => <RankRow key={it.spuId} item={it} idx={i} metric={metric} tone={tone} onOpen={onOpen} />)
      )}
    </div>
  )
}

function Ranking({ rankings, onOpen }) {
  return (
    <div className="ranking">
      <RankColumn title="🔥 溢价榜" note="溢价率最高" items={rankings.premiumTop}
        metric={(p) => fmtPct(p.premiumPct)} tone="up" onOpen={onOpen} />
      <RankColumn title="💎 捡漏榜" note="低于发售价最多" items={rankings.discountTop}
        metric={(p) => fmtPct(p.premiumPct)} tone="down" onOpen={onOpen} />
      <RankColumn title="💰 高价榜" note="市场价最高" items={rankings.priceTop}
        metric={(p) => fmt(p.latestPrice)} tone="" onOpen={onOpen} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// 搬砖套利机会
// ---------------------------------------------------------------------------
function ArbitrageList({ opps, platforms, scanning, onScan }) {
  if (scanning) return <Skeleton n={5} />
  if (!opps.length) {
    return (
      <div className="empty">
        <div className="empty-icon">🔄</div>
        <div className="empty-title">暂无套利机会</div>
        <div>点击「扫描搬砖」抓取得物热门商品，自动到 {platforms.join('、') || '各平台'} 比价找差价</div>
        {!IS_STATIC && <button className="primary-btn big-empty" onClick={onScan}>🔍 扫描搬砖机会</button>}
      </div>
    )
  }
  return (
    <>
      <div className="arb-head">
        <div className="arb-head-info">
          发现 <b>{opps.length}</b> 个套利机会（利润率从高到低）
          <span className="sec-note">利润 = 得物到手价 − 平台买入价 − 运费</span>
        </div>
        {!IS_STATIC && <button className="collect-btn" onClick={onScan}>↻ 重新扫描</button>}
      </div>
      <div className="arb-list">
        {opps.map((o, i) => (
          <div className="arb-card" key={o.articleNumber + i}>
            <div className="arb-rank">#{i + 1}</div>
            {o.logoUrl ? <img className="arb-img" src={o.logoUrl} alt="" loading="lazy" /> : <span className="arb-img noimg" />}
            <div className="arb-info">
              <div className="arb-title" title={o.title}>{o.title || '—'}</div>
              <div className="arb-code">货号 {o.articleNumber} {o.dewuSales ? `· ${o.dewuSales}` : ''}</div>
              <div className="arb-flow">
                <span className="flow-from">得物卖出 <b>{fmt(o.dewuPrice)}</b></span>
                <span className="flow-arrow">→ 到手 {fmt(o.netPrice)}</span>
                <span className="flow-to">{o.bestBuy?.platform}买入 <b>{fmt(o.bestBuy?.price)}</b></span>
              </div>
            </div>
            <div className="arb-profit">
              <div className="profit-val">+{fmt(o.profit)}</div>
              <div className="profit-rate">{fmtPct(o.profitRate)}</div>
              {o.bestBuy?.link ? (
                <a className="profit-link" href={o.bestBuy.link} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>去买入 ↗</a>
              ) : null}
            </div>
          </div>
        ))}
      </div>
    </>
  )
}

// ---------------------------------------------------------------------------
// 详情弹窗
// ---------------------------------------------------------------------------
function Detail({ selected, onClose, onToggleWatch, alertPrice, setAlertPrice }) {
  const chans = useMemo(() => {
    const r = {}
    for (const c of CHANNELS) {
      const v = channelMin(selected?.skus, c.key)
      if (v != null) r[c.key] = { ...c, min: v }
    }
    return Object.values(r)
  }, [selected])

  const change = selected?.priceChange || 0
  const pct = selected?.priceChangePct || 0
  const trend = change > 0 ? 1 : change < 0 ? -1 : 0

  return (
    <div className="modal" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <button className="close" onClick={onClose}>×</button>
        <div className="detail-top">
          <div className="detail-img">
            {selected?.logoUrl ? <img src={selected.logoUrl} alt={selected.title} /> : <div className="noimg">无图</div>}
          </div>
          <div className="detail-main">
            <div className="detail-head">
              <h2>{selected?.title || '—'}</h2>
              {selected?.brand && <span className="tag">{selected.brand}</span>}
            </div>
            <div className="detail-meta">
              {selected?.articleNumber && <span>货号 <b>{selected.articleNumber}</b></span>}
              {selected?.sellDate && <span>发售 <b>{selected.sellDate}</b></span>}
              {selected?.soldCountText && <span>{selected.soldCountText}</span>}
            </div>
            <div className="price-hero">
              <div className="hero-left">
                <div className="hero-label">最新价</div>
                <div className={`hero-price ${trend > 0 ? 'up' : trend < 0 ? 'down' : ''}`}>{fmt(selected?.latestPrice)}</div>
                <div className={`delta big ${trend > 0 ? 'up' : trend < 0 ? 'down' : ''}`}>
                  {trend > 0 ? '▲' : trend < 0 ? '▼' : '—'} {fmt(selected?.priceChange)} ({fmtPct(pct)})
                </div>
              </div>
              <div className="hero-right">
                <div className="mini-stat"><span className="k">发售价</span><span className="v">{fmt(selected?.authPrice)}</span></div>
                <div className="mini-stat"><span className="k">历史最高</span><span className="v">{fmt(selected?.maxPrice)}</span></div>
                <div className="mini-stat"><span className="k">历史最低</span><span className="v">{fmt(selected?.minPrice)}</span></div>
                <div className="mini-stat">
                  <span className="k">溢价率</span>
                  <span className={`v ${upOf(selected?.premiumPct) ? 'up' : 'down'}`}>{selected?.premiumPct == null ? '—' : fmtPct(selected.premiumPct)}</span>
                </div>
              </div>
            </div>
            <div className="watch-row">
              {!IS_STATIC && (
                <button className={`watch-pill big ${selected?.watched ? 'on' : ''}`} onClick={onToggleWatch}>
                  {selected?.watched ? '✓ 监控中' : '+ 加入监控'}
                </button>
              )}
              {IS_STATIC && selected?.watched ? <span className="watch-pill big on">✓ 监控中</span> : null}
              {!IS_STATIC && (
                <div className="alert-input">
                  <label>告警价</label>
                  <input type="number" placeholder="低于此价提醒" value={alertPrice} onChange={(e) => setAlertPrice(e.target.value)} />
                </div>
              )}
              {IS_STATIC && <span className="hint">监控与告警通过仓库 watchlist.json 配置</span>}
            </div>
          </div>
        </div>

        {chans.length > 0 && (
          <div className="section">
            <h3>渠道报价 <span className="sec-note">各渠道最低价</span></h3>
            <div className="channel-grid">
              {chans.map((c) => (
                <div className="channel-card" key={c.key} style={{ '--c': c.color }}>
                  <div className="channel-name">{c.label}</div>
                  <div className="channel-price">{fmt(c.min)}</div>
                  <div className="channel-desc">{c.desc}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="section">
          <h3>尺码价格</h3>
          {selected?.skus && selected.skus.length > 0 ? (
            <div className="size-grid">
              {selected.skus.map((s) => (
                <div className="size-item" key={s.skuId}>
                  <div className="size">{s.size || s.skuId}</div>
                  <div className="size-price">{fmt(s['普通发货'] ?? s['闪电直发'] ?? s['极速发货'])}</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty small">该商品暂无尺码报价（首页采集的商品需在住宅网络下抓取详情）</div>
          )}
        </div>

        <div className="section">
          <h3>价格走势 <span className="sec-note">虚线为发售价</span></h3>
          {selected?.history && selected.history.length > 0 ? (
            <PriceChart history={selected.history} authPrice={selected.authPrice} />
          ) : (
            <div className="empty small">暂无历史价格</div>
          )}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// 通知设置弹窗
// ---------------------------------------------------------------------------
function NotifyModal({ notify, setNotify, onClose, onSave, onTest, testing }) {
  const up = (k, v) => setNotify({ ...notify, [k]: v })
  const field = (key, label, placeholder) => (
    <div className="form-field">
      <label>{label}</label>
      <input value={notify[key] || ''} onChange={(e) => up(key, e.target.value)} placeholder={placeholder} />
    </div>
  )
  return (
    <div className="modal" onClick={onClose}>
      <div className="modal-card narrow" onClick={(e) => e.stopPropagation()}>
        <button className="close" onClick={onClose}>×</button>
        <h2 className="modal-title">推送通知设置</h2>
        <p className="modal-desc">价格跌破告警价时，自动推送提醒到手机</p>

        <div className="form-field">
          <label>推送渠道</label>
          <div className="channel-tabs">
            {[['bark', 'Bark (iOS)'], ['serverchan', 'Server酱'], ['dingtalk', '钉钉机器人'], ['webhook', '自定义 Webhook']].map(([k, l]) => (
              <button key={k} className={notify.channel === k ? 'active' : ''} onClick={() => up('channel', k)}>{l}</button>
            ))}
          </div>
        </div>

        {notify.channel === 'bark' && field('bark_url', 'Bark 地址', 'https://api.day.app/你的Key')}
        {notify.channel === 'serverchan' && field('serverchan_key', 'Server酱 SendKey', 'SCT...')}
        {notify.channel === 'dingtalk' && field('dingtalk_webhook', '钉钉机器人 Webhook', 'https://oapi.dingtalk.com/robot/send?access_token=...')}
        {notify.channel === 'webhook' && field('webhook_url', 'Webhook 地址', 'https://example.com/hook')}

        <div className="form-actions">
          <label className="switch">
            <input type="checkbox" checked={!!notify.enabled} onChange={(e) => up('enabled', e.target.checked)} />
            <span>{notify.enabled ? '已启用' : '未启用'}</span>
          </label>
          <div className="spacer" />
          <button className="ghost-btn" onClick={onTest} disabled={testing}>{testing ? '发送中…' : '发送测试'}</button>
          <button className="primary-btn" onClick={onSave}>保存</button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// 主应用
// ---------------------------------------------------------------------------
export default function App() {
  const [tab, setTab] = useState('market')
  const [query, setQuery] = useState('')
  const [searchResults, setSearchResults] = useState([])
  const [searchTotal, setSearchTotal] = useState(null)
  const [products, setProducts] = useState([])
  const [stats, setStats] = useState(null)
  const [alerts, setAlerts] = useState([])
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [alertPrice, setAlertPrice] = useState('')
  const [polling, setPolling] = useState(false)
  const [collecting, setCollecting] = useState(false)
  const [online, setOnline] = useState(false)
  const [showNotify, setShowNotify] = useState(false)
  const [notify, setNotify] = useState({ channel: 'bark', enabled: false })
  const [testing, setTesting] = useState(false)
  const [sortKey, setSortKey] = useState('time')
  const [opps, setOpps] = useState([])
  const [arbPlatforms, setArbPlatforms] = useState([])
  const [scanning, setScanning] = useState(false)

  const loadAll = async () => {
    try {
      const [p, s, al] = await Promise.all([api.listProducts(false), api.stats(), api.alerts(50)])
      setProducts(p.items || [])
      setStats(s)
      setAlerts(al.items || [])
      setOnline(true)
    } catch (e) { setOnline(false); setError(e.message) }
  }

  const loadNotify = async () => {
    try {
      const r = await api.getSettings()
      setNotify(r.notify || { channel: 'bark', enabled: false })
    } catch (e) { setError(e.message) }
  }

  useEffect(() => { loadAll(); loadNotify() }, [])

  const watched = useMemo(() => products.filter((p) => p.watched), [products])

  const sorted = useMemo(() => {
    const arr = [...products]
    if (sortKey === 'up') arr.sort((a, b) => (b.priceChangePct || 0) - (a.priceChangePct || 0))
    else if (sortKey === 'down') arr.sort((a, b) => (a.priceChangePct || 0) - (b.priceChangePct || 0))
    else if (sortKey === 'premium') arr.sort((a, b) => (b.premiumPct || -Infinity) - (a.premiumPct || -Infinity))
    else if (sortKey === 'price') arr.sort((a, b) => (b.latestPrice || 0) - (a.latestPrice || 0))
    return arr
  }, [products, sortKey])

  // 榜单（top N）
  const rankings = useMemo(() => {
    const withPremium = products.filter((p) => p.premiumPct != null)
    const premiumTop = [...withPremium].sort((a, b) => b.premiumPct - a.premiumPct).slice(0, 8)
    const discountTop = [...withPremium].sort((a, b) => a.premiumPct - b.premiumPct).slice(0, 8)
    const priceTop = products.filter((p) => p.latestPrice != null)
      .sort((a, b) => b.latestPrice - a.latestPrice).slice(0, 8)
    return { premiumTop, discountTop, priceTop }
  }, [products])

  const doSearch = async () => {
    if (!query.trim()) return
    setLoading(true); setError('')
    try {
      const r = await api.search(query.trim())
      setSearchResults(r.items || [])
      setSearchTotal(r.total)
      setTab('search')
    } catch (e) { setError(e.message) } finally { setLoading(false) }
  }

  const openProduct = async (p) => {
    setLoading(true); setError(''); setAlertPrice('')
    try {
      let id = p.id
      if (!id) { const r = await api.fetchProduct({ spuId: p.spuId }); id = r.productId }
      const detail = await api.getProduct(id)
      setSelected(detail)
      setAlertPrice(detail.alertPrice ? String(detail.alertPrice) : '')
    } catch (e) { setError(e.message) } finally { setLoading(false) }
  }

  const toggleWatch = async (p, watchedVal) => {
    try {
      let id = p.id
      if (!id) { const r = await api.fetchProduct({ spuId: p.spuId }); id = r.productId }
      const alert = alertPrice ? parseFloat(alertPrice) : (p.alertPrice || 0)
      await api.setWatch(id, watchedVal, alert || 0)
      if (selected && selected.id === id) setSelected({ ...selected, watched: watchedVal ? 1 : 0 })
      await loadAll()
    } catch (e) { setError(e.message) }
  }

  const doPoll = async () => {
    setPolling(true); setError('')
    try {
      const r = await api.poll()
      setNotice(`轮询完成：成功 ${r.ok}，失败 ${r.fail}`)
      await loadAll()
    } catch (e) { setError(e.message) } finally { setPolling(false) }
  }

  const doCollect = async () => {
    setCollecting(true); setError(''); setNotice('')
    try {
      const r = await api.collect(3, 20)
      setNotice(`✅ 已采集 ${r.collected} 个热门商品`)
      await loadAll()
      setTab('market')
    } catch (e) { setError(e.message) } finally { setCollecting(false) }
  }

  const doArbitrage = async () => {
    setScanning(true); setError(''); setNotice('')
    setTab('arbitrage')
    try {
      const r = await api.arbitrage(3, 0)
      setOpps(r.opportunities || [])
      setArbPlatforms(r.platforms || [])
      setNotice(`扫描完成：发现 ${r.opportunities?.length || 0} 个套利机会`)
    } catch (e) { setError(e.message) } finally { setScanning(false) }
  }

  const saveNotify = async () => {
    try { await api.saveSettings(notify); setNotice('通知设置已保存'); setShowNotify(false) }
    catch (e) { setError(e.message) }
  }
  const testNotify = async () => {
    setTesting(true); setError('')
    try {
      const r = await api.notifyTest()
      setNotice(r.ok ? '✅ 测试通知已发送，请查收手机' : `❌ 发送失败：${r.error || JSON.stringify(r)}`)
    } catch (e) { setError(e.message) } finally { setTesting(false) }
  }

  const list = tab === 'watched' ? watched : sorted

  return (
    <div className="app">
      <header className="header">
        <div className="brand">
          <div className="brand-mark">得</div>
          <div className="brand-text">
            <div className="brand-name">得物雷达</div>
            <div className="brand-sub">Dewu Market Monitor</div>
          </div>
        </div>
        <div className="search-box">
          <span className="search-icon">⌕</span>
          <input value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && doSearch()}
            placeholder="搜索鞋款 / 货号（也可直接点下方「采集热门」）" />
          <button onClick={doSearch} disabled={loading}>搜索</button>
        </div>
        <div className="header-right">
          {IS_STATIC && <span className="static-badge">静态数据</span>}
          <span className={`online-dot ${online ? 'on' : 'off'}`} />
          <span className="online-text">{online ? '已连接' : '离线'}</span>
          {stats && <span className="watch-count">{stats.watched} 监控</span>}
        </div>
      </header>

      <div className="stats-bar">
        <StatCard label="监控中" value={stats?.watched} sub="活跃监控商品" tone="accent" />
        <StatCard label="商品总数" value={stats?.total} sub="已收录商品" />
        <StatCard label="今日上涨" value={stats?.up} sub="较上次轮询" tone="up" />
        <StatCard label="今日下跌" value={stats?.down} sub="较上次轮询" tone="down" />
        <StatCard label="平均溢价" value={stats?.avgPremium == null ? '—' : fmtPct(stats.avgPremium)} sub="相对发售价" tone={upOf(stats?.avgPremium) ? 'up' : 'down'} />
      </div>

      <div className="tabs">
        <button className={tab === 'market' ? 'active' : ''} onClick={() => setTab('market')}>行情 · {products.length}</button>
        <button className={tab === 'ranking' ? 'active' : ''} onClick={() => setTab('ranking')}>榜单</button>
        <button className={tab === 'arbitrage' ? 'active' : ''} onClick={doArbitrage}>搬砖套利</button>
        <button className={tab === 'watched' ? 'active' : ''} onClick={() => setTab('watched')}>监控中 · {watched.length}</button>
        <button className={tab === 'search' ? 'active' : ''} onClick={() => setTab('search')}>搜索{searchTotal != null ? ` · ${searchTotal}` : ''}</button>
        <button className={tab === 'alerts' ? 'active' : ''} onClick={() => setTab('alerts')}>告警 · {alerts.length}</button>
        <div className="spacer" />

        <select className="sort-select" value={sortKey} onChange={(e) => setSortKey(e.target.value)}>
          <option value="time">按时间</option>
          <option value="up">涨幅榜</option>
          <option value="down">跌幅榜</option>
          <option value="premium">溢价榜</option>
          <option value="price">价格榜</option>
        </select>

        {!IS_STATIC && <button className="ghost-btn" onClick={() => { setShowNotify(true); loadNotify() }}>🔔 推送设置</button>}
        {!IS_STATIC && <button className="collect-btn" onClick={doCollect} disabled={collecting}>{collecting ? '采集ing…' : '⚡ 采集热门'}</button>}
        {!IS_STATIC && <button className="poll-btn" onClick={doPoll} disabled={polling}>{polling ? '⟳ 轮询中…' : '⟳ 轮询'}</button>}
      </div>

      {error && <div className="banner">{error}</div>}
      {notice && <div className="notice">{notice}</div>}

      <main className="content">
        {loading && <Skeleton />}

        {!loading && tab === 'search' && (
          searchResults.length === 0 ? (
            <div className="empty"><div className="empty-icon">📡</div><div className="empty-title">搜索商品</div>
              <div>输入关键词搜索，或点击右上角「采集热门」自动收录一批热门商品</div></div>
          ) : (
            <div className="grid">{searchResults.map((p) => (
              <ProductCard key={p.spuId} p={p} onOpen={openProduct} onToggleWatch={(p) => toggleWatch(p, true)} />
            ))}</div>
          )
        )}

        {!loading && tab === 'ranking' && (
          <Ranking rankings={rankings} onOpen={openProduct} />
        )}

        {!loading && tab === 'arbitrage' && (
          <ArbitrageList opps={opps} platforms={arbPlatforms} scanning={scanning} onScan={doArbitrage} />
        )}

        {!loading && (tab === 'market' || tab === 'watched') && (
          list.length === 0 ? (
            <div className="empty"><div className="empty-icon">🛰️</div>
              <div className="empty-title">{tab === 'watched' ? '暂无监控' : '还没有商品'}</div>
              {IS_STATIC ? (
                <div>暂无数据，等待 GitHub Actions 定时抓取后自动更新</div>
              ) : (
                <>
                  <div>点击右上角「⚡ 采集热门」一键收录得物热门商品，再逐个加入监控</div>
                  <button className="primary-btn big-empty" onClick={doCollect}>{collecting ? '采集中…' : '⚡ 立即采集热门商品'}</button>
                </>
              )}
            </div>
          ) : (
            <div className="grid">{list.map((p) => (
              <ProductCard key={p.id} p={p} onOpen={openProduct} onToggleWatch={(p) => toggleWatch(p, !p.watched)} />
            ))}</div>
          )
        )}

        {!loading && tab === 'alerts' && (
          alerts.length === 0 ? (
            <div className="empty"><div className="empty-icon">🔕</div><div className="empty-title">暂无告警</div>
              <div>给监控商品设置「告警价」，价格跌破时会在这里记录并推送通知</div></div>
          ) : (
            <div className="alert-list">
              {alerts.map((a) => (
                <div className="alert-item" key={a.id}>
                  <div className="alert-title">{a.title || a.spuId}</div>
                  <div className="alert-prices">当前 {fmt(a.price)} · 阈值 {fmt(a.alertPrice)}</div>
                  <div className="alert-meta">
                    <span className={`tag ${a.sent ? 'sent' : 'unsent'}`}>{a.sent ? '已推送' : '未推送'}</span>
                    <span className="tag">{a.channel || '无渠道'}</span>
                    <span className="alert-time">{new Date(a.created_at * 1000).toLocaleString()}</span>
                  </div>
                </div>
              ))}
            </div>
          )
        )}
      </main>

      {selected && (
        <Detail selected={selected} onClose={() => setSelected(null)}
          onToggleWatch={() => toggleWatch(selected, !selected.watched)}
          alertPrice={alertPrice} setAlertPrice={setAlertPrice} />
      )}

      {showNotify && (
        <NotifyModal notify={notify} setNotify={setNotify} onClose={() => setShowNotify(false)}
          onSave={saveNotify} onTest={testNotify} testing={testing} />
      )}
    </div>
  )
}
