interface CommuteEstimate {
  commute_minutes?: number | null
  commute_distance_m?: number | null
  commute_origin?: string | null
  commute_mode?: string | null
  commute_checked_at?: string | null
}

function validMeasure(value?: number | null): value is number {
  return typeof value === 'number' && Number.isFinite(value) && Number.isInteger(value) && value >= 0
}

function measures(job: CommuteEstimate) {
  const hasOrigin = Boolean(job.commute_origin?.trim())
  return {
    minutes: hasOrigin && validMeasure(job.commute_minutes) ? job.commute_minutes : null,
    distance: hasOrigin && validMeasure(job.commute_distance_m) ? job.commute_distance_m : null,
  }
}

function distanceLabel(meters: number) {
  if (meters === 0) return '0 公里'
  const rounded = Math.round(meters / 100) / 10
  return rounded === 0 ? '<0.1 公里' : `${rounded.toFixed(1)} 公里`
}

export function commuteLabel(job: CommuteEstimate) {
  const { minutes, distance } = measures(job)
  if (minutes === null && distance === null) return '通勤待核实'
  return `约 ${[distance !== null ? distanceLabel(distance) : null, minutes !== null ? `${minutes} 分钟` : null].filter(Boolean).join(' · ')}`
}

export function commuteDescription(job: CommuteEstimate) {
  const { minutes, distance } = measures(job)
  if (minutes === null && distance === null) return '单程通勤：待核实，尚无地图估算'
  const checked = job.commute_checked_at ? `，核于 ${job.commute_checked_at.slice(0, 10)}` : ''
  const details = [distance !== null ? distanceLabel(distance) : '距离待核实', minutes !== null ? `${minutes} 分钟` : '时间待核实'].join(' · ')
  return `单程通勤：从${job.commute_origin?.trim()}，${details}（${job.commute_mode || '公共交通'}，地图估算${checked}）`
}

const routeParams = new Set(['r', 'from', 'to', 'mode', 'policy', 'src', 'callnative', 'type', 'innersrc'])

export function safeCommuteSourceUrl(value?: string | null): string | null {
  if (!value || value !== value.trim() || /[\u0000-\u0020\u007f]/.test(value)) return null
  try {
    const url = new URL(value)
    const authority = value.match(/^https:\/\/([^/]+)/i)?.[1]
    if (!authority || authority.includes(':')) return null
    if (url.protocol !== 'https:' || url.username || url.password || url.port || url.hash) return null
    const validRoute = (url.hostname === 'www.amap.com' && url.pathname === '/')
      || (url.hostname === 'uri.amap.com' && url.pathname === '/navigation')
      || (url.hostname === 'ditu.amap.com' && url.pathname === '/dir')
    if (!validRoute) return null
    if (url.search && url.search.slice(1).split('&').some(pair => !pair.includes('='))) return null
    for (const key of url.searchParams.keys()) {
      if (!routeParams.has(key) && !/^(?:from|to)\[(?:name|lnglat)\]$/.test(key)) return null
    }
    return url.toString()
  } catch {
    return null
  }
}
