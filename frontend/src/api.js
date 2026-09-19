// 双模式 API 层：
// - 开发模式（npm run dev）：请求本地后端 /api/*
// - 生产模式（GitHub Pages）：读取静态 data/*.json（由 scripts/collect.py 生成）
const IS_DEV = import.meta.env.DEV
const API_BASE = '/api'
const DATA_BASE = import.meta.env.BASE_URL.replace(/\/$/, '') + '/data'

async function request(path, options = {}) {
  const res = await fetch(API_BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const j = await res.json()
      detail = j.detail || JSON.stringify(j)
    } catch {}
    throw new Error(detail)
  }
  return res.json()
}

// 静态数据缓存
let _cache = null
async function loadStatic() {
  if (_cache) return _cache
  const get = (f) => fetch(`${DATA_BASE}/${f}.json`).then((r) => r.json())
  const [products, stats, history, alerts] = await Promise.all([
    get('products'), get('stats'), get('history'), get('alerts'),
  ])
  _cache = { products, stats, history, alerts }
  return _cache
}

export const api = {
  health: () => (IS_DEV ? request('/health') : Promise.resolve({ status: 'ok', static: true })),

  search: async (q, page = 0, limit = 20) => {
    if (IS_DEV) return request(`/search?q=${encodeURIComponent(q)}&page=${page}&limit=${limit}`)
    const { products } = await loadStatic()
    const kw = q.toLowerCase()
    const items = (products.items || []).filter(
      (p) =>
        (p.title || '').toLowerCase().includes(kw) ||
        (p.articleNumber || '').toLowerCase().includes(kw),
    )
    return { items: items.slice(page * limit, (page + 1) * limit), total: items.length }
  },

  fetchProduct: (payload) =>
    IS_DEV
      ? request('/products/fetch', { method: 'POST', body: JSON.stringify(payload) })
      : Promise.reject(new Error('静态模式不支持抓取')),

  listProducts: async () => {
    if (IS_DEV) return request('/products')
    const { products } = await loadStatic()
    return products
  },

  stats: async () => {
    if (IS_DEV) return request('/stats')
    const { stats } = await loadStatic()
    return stats
  },

  getProduct: async (id) => {
    if (IS_DEV) return request(`/products/${id}`)
    const { products, history } = await loadStatic()
    const p = (products.items || []).find((x) => x.id === Number(id))
    if (!p) throw new Error('商品不存在')
    const h = history[p.spuId] || []
    return { ...p, history: h.map((x) => ({ price: x.price, ts: x.ts })) }
  },

  setWatch: (id, watched, alert_price = 0) =>
    IS_DEV
      ? request(`/products/${id}/watch`, { method: 'POST', body: JSON.stringify({ watched, alert_price }) })
      : Promise.resolve({ ok: true }),

  getHistory: (id, limit = 200) =>
    IS_DEV ? request(`/products/${id}/history?limit=${limit}`) : Promise.resolve({ items: [] }),

  poll: () => (IS_DEV ? request('/poll', { method: 'POST' }) : Promise.reject(new Error('静态模式不支持'))),
  collect: () => (IS_DEV ? request('/collect', { method: 'POST', body: JSON.stringify({ pages: 3, limit: 20 }) }) : Promise.reject(new Error('静态模式不支持'))),

  getSettings: () => (IS_DEV ? request('/settings') : Promise.resolve({ notify: {} })),
  saveSettings: (notify) =>
    IS_DEV ? request('/settings', { method: 'POST', body: JSON.stringify({ config: { notify } }) }) : Promise.resolve({ ok: true }),
  notifyTest: () => (IS_DEV ? request('/notify/test', { method: 'POST' }) : Promise.reject(new Error('静态模式不支持'))),

  alerts: async (limit = 100) => {
    if (IS_DEV) return request(`/alerts?limit=${limit}`)
    const { alerts } = await loadStatic()
    return alerts
  },

  arbitrage: (pages = 3, minRate = 0) =>
    IS_DEV ? request(`/arbitrage?pages=${pages}&min_rate=${minRate}`) : Promise.resolve({ opportunities: [] }),
}

export { IS_DEV }
