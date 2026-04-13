import { ChartData } from '@/types/chat'

/**
 * Detects chart data in an AI response text.
 * Looks for BAR_CHART:/PIE_CHART:/LINE_CHART: prefixes and bullet-point numeric data.
 */
export function detectChartData(text: string): ChartData | null {
  const lines = text.split('\n')

  // Detect explicit chart type
  let chartType: ChartData['chartType'] = 'bar'
  const firstLine = lines[0]?.trim().toUpperCase() ?? ''
  if (firstLine.startsWith('PIE_CHART:') || text.toLowerCase().includes('pie chart')) {
    chartType = 'pie'
  } else if (firstLine.startsWith('LINE_CHART:')) {
    chartType = 'line'
  }

  // Extract numeric pairs from bullet points
  const pairs: { label: string; value: number }[] = []
  for (const line of lines) {
    const m = line.match(/[-*]\s*([^:]{2,35}):\s*[\$]?([\d,.]+)\s*([MKBmkb])?/)
    if (!m) continue
    let value = parseFloat(m[2].replace(/,/g, ''))
    const suffix = (m[3] ?? '').toUpperCase()
    if (suffix === 'K') value /= 1000
    if (suffix === 'B') value *= 1000
    const label = m[1].trim()
      .replace(/\*+/g, '')
      .replace(/^(BAR|PIE|LINE)_CHART:?/i, '')
      .trim()
    if (!isNaN(value) && value > 0 && value < 100_000 && label.length > 1) {
      pairs.push({ label, value })
    }
  }

  if (pairs.length < 2) return null

  return {
    labels: pairs.map((p) => p.label),
    values: pairs.map((p) => p.value),
    chartType,
  }
}

/** Downloads an SVG element as a PNG file. */
export function downloadSvgAsPng(elementId: string, filename = 'chart.png'): void {
  const el = document.getElementById(elementId) as SVGSVGElement | null
  if (!el) return
  const serializer = new XMLSerializer()
  const svgStr = serializer.serializeToString(el)
  const canvas = document.createElement('canvas')
  canvas.width = el.width.baseVal.value * 2
  canvas.height = el.height.baseVal.value * 2
  const ctx = canvas.getContext('2d')!
  const img = new Image()
  img.onload = () => {
    ctx.scale(2, 2)
    ctx.drawImage(img, 0, 0)
    const a = document.createElement('a')
    a.download = filename
    a.href = canvas.toDataURL('image/png')
    a.click()
  }
  img.src = 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(svgStr)))
}
