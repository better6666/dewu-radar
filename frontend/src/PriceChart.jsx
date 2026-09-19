import React, { useEffect, useRef } from 'react'
import * as echarts from 'echarts'

export default function PriceChart({ history, authPrice }) {
  const ref = useRef(null)
  const chartRef = useRef(null)

  useEffect(() => {
    if (!ref.current) return
    if (!chartRef.current) chartRef.current = echarts.init(ref.current)
    const chart = chartRef.current

    const data = (history || [])
      .filter((h) => h.price != null)
      .map((h) => ({ t: new Date(h.ts * 1000), v: h.price }))
      .sort((a, b) => a.t - b.t)

    const first = data[0]?.v
    const last = data[data.length - 1]?.v
    const up = last != null && first != null && last >= first
    const lineColor = up ? '#f43f5e' : '#10b981'

    chart.setOption({
      backgroundColor: 'transparent',
      grid: { left: 48, right: 20, top: 24, bottom: 34 },
      tooltip: {
        trigger: 'axis',
        backgroundColor: '#141c2b',
        borderColor: '#243047',
        textStyle: { color: '#e5edf5', fontSize: 12 },
        valueFormatter: (v) => (v == null ? '-' : '¥' + Number(v).toFixed(2)),
      },
      xAxis: {
        type: 'time',
        axisLine: { lineStyle: { color: '#243047' } },
        axisLabel: { color: '#8b98ad', hideOverlap: true },
      },
      yAxis: {
        type: 'value',
        scale: true,
        axisLabel: { color: '#8b98ad', formatter: '¥{value}' },
        splitLine: { lineStyle: { color: '#1a2335' } },
      },
      series: [
        {
          name: '价格',
          type: 'line',
          data: data.map((d) => [d.t, d.v]),
          smooth: true,
          showSymbol: false,
          lineStyle: { color: lineColor, width: 2.4 },
          itemStyle: { color: lineColor },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: up ? 'rgba(244,63,94,0.22)' : 'rgba(16,185,129,0.22)' },
              { offset: 1, color: 'rgba(0,0,0,0)' },
            ]),
          },
          markLine: authPrice ? {
            silent: true,
            symbol: 'none',
            lineStyle: { color: '#f5c542', type: 'dashed', width: 1.2 },
            label: { color: '#f5c542', formatter: '发售价 ¥' + Number(authPrice).toFixed(2), position: 'insideEndTop' },
            data: [{ yAxis: authPrice }],
          } : undefined,
        },
      ],
    })

    const onResize = () => chart.resize()
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [history, authPrice])

  return <div ref={ref} style={{ width: '100%', height: 300 }} />
}
