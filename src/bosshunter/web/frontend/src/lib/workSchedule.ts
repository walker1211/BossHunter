export type WorkSchedule = 'double' | 'alternate' | 'single' | 'unclear' | 'unknown'

export function workScheduleSourceLabel(source?: string) {
  switch (source) {
    case 'job_posting': return '职位文案'
    case 'company_profile': return '公司页（福利/简介）'
    case 'manual': return '人工记录'
    case '':
    case undefined: return '未记录'
    default: return `其他来源（${source}）`
  }
}

export function workScheduleLabel(schedule?: WorkSchedule, source?: string) {
  const prefix = source === 'company_profile' ? '公司页称' : source === 'manual' ? '人工记录称' : source && source !== 'job_posting' ? '来源称' : '文案称'
  switch (schedule) {
    case 'double': return `${prefix}双休`
    case 'alternate': return `${prefix}大小周`
    case 'single': return `${prefix}单休`
    case 'unclear': return '表述冲突'
    default: return '未说明'
  }
}

export function workScheduleDescription(schedule?: WorkSchedule, source?: string) {
  return `${workScheduleLabel(schedule, source)}（来源：${workScheduleSourceLabel(source)}）；尚未向招聘方核实`
}

export function safeCompanyProfileUrl(url?: string | null): string | null {
  if (!url) return null
  try {
    const parsed = new URL(url, 'https://www.zhipin.com')
    if (parsed.protocol !== 'https:' || parsed.username || parsed.password || parsed.port) return null
    if (parsed.hostname !== 'zhipin.com' && parsed.hostname !== 'www.zhipin.com') return null
    if (!/^\/gongsi\/[A-Za-z0-9_~-]+\.html$/.test(parsed.pathname)) return null
    return `https://www.zhipin.com${parsed.pathname}`
  } catch {
    return null
  }
}
