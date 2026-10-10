import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { JobsTable } from './JobsTable'
import type { Job } from '@/hooks/useDashboard'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function mockTextOverflow() {
  vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(144)
  vi.spyOn(HTMLElement.prototype, 'scrollHeight', 'get').mockImplementation(function (this: HTMLElement) {
    return (this.textContent?.length || 0) > 80 ? 240 : 24
  })
}

function showJob(overrides: Partial<Job> = {}) {
  const job = {
    id: 'example', company: '示例公司', title: '后端开发', salary: '20-30K', city: '深圳',
    jd: '负责API', status: 'scored', score: 82, created_at: '', hr_active: '今日活跃',
    work_schedule: 'double', work_schedule_source: 'company_profile', work_schedule_evidence: '工作时间及福利：双休',
    company_url: 'https://www.zhipin.com/gongsi/example.html?ka=tracking',
    ...overrides,
  } as Job
  render(<JobsTable jobs={[job]} page={0} pageSize={15} total={1} onPageChange={vi.fn()}
    selectedIds={[]} onToggleSelected={vi.fn()} sortBy="created_at" sortOrder="desc" onSortChange={vi.fn()} />)
  fireEvent.click(screen.getByText('示例公司'))
}

describe('work schedule evidence in the job pool', () => {
  it('lets a user open the row to read company evidence and its original page', () => {
    showJob()
    expect(screen.getByText('公司页称双休')).toBeTruthy()
    expect(screen.getByText(/来源：公司页.*尚未向招聘方核实/)).toBeTruthy()
    expect(screen.getByText('原文依据：工作时间及福利：双休')).toBeTruthy()
    expect(screen.getByRole('link', { name: '原公司页链接' }).getAttribute('href')).toBe('https://www.zhipin.com/gongsi/example.html')
    const toggle = screen.getByRole('button', { name: '收起 示例公司 后端开发 详情' })
    expect(toggle.getAttribute('aria-expanded')).toBe('true')
    expect(document.getElementById(toggle.getAttribute('aria-controls')!)).toBeTruthy()
    fireEvent.click(toggle)
    expect(screen.getByRole('button', { name: '展开 示例公司 后端开发 详情' }).getAttribute('aria-expanded')).toBe('false')
    expect(screen.queryByRole('link', { name: '原公司页链接' })).toBeNull()
  })

  it('keeps unknown schedules visible and rejects unsafe source links', () => {
    showJob({ work_schedule: 'unknown', work_schedule_source: '', work_schedule_evidence: '', company_url: 'javascript:alert(1)' })
    expect(screen.getByText('未说明')).toBeTruthy()
    expect(screen.getByText('原文依据：未记录')).toBeTruthy()
    expect(screen.queryByRole('link', { name: '原公司页链接' })).toBeNull()
    expect(screen.getByText('通勤待核实')).toBeTruthy()
    expect(screen.getByText('单程通勤：待核实，尚无地图估算')).toBeTruthy()
  })

  it('keeps saved transit estimates and office locations accessible', () => {
    showJob({ commute_origin: '示例站', commute_minutes: 42, commute_mode: '地铁', commute_checked_at: '2026-10-01', work_location: '示例园区' })
    expect(screen.getByText('约 42 分钟')).toBeTruthy()
    expect(screen.getByText('办公地点：示例园区')).toBeTruthy()
    expect(screen.getByText('单程通勤：从示例站，距离待核实 · 42 分钟（地铁，地图估算，核于 2026-10-01）')).toBeTruthy()
  })

  it('shows route distance and links the original map only when safe', () => {
    showJob({ commute_origin: '示例站', commute_distance_m: 12345, commute_minutes: 42,
      commute_source_url: 'https://uri.amap.com/navigation?from=A&to=B&mode=bus' })
    expect(screen.getByText('约 12.3 公里 · 42 分钟')).toBeTruthy()
    const link = screen.getByRole('link', { name: '查看原地图路线' })
    expect(link.getAttribute('href')).toBe('https://uri.amap.com/navigation?from=A&to=B&mode=bus')
    expect(link.getAttribute('rel')).toBe('noopener noreferrer')
  })

  it('omits unsafe route links while keeping distance only estimates', () => {
    showJob({ commute_origin: '示例站', commute_distance_m: 20, commute_source_url: 'https://www.amap.com/?key=secret' })
    expect(screen.getByText('约 <0.1 公里')).toBeTruthy()
    expect(screen.getByText(/时间待核实/)).toBeTruthy()
    expect(screen.queryByRole('link', { name: '查看原地图路线' })).toBeNull()
  })
})

describe('job detail long text', () => {
  it('expands JD and score reason independently while keeping the full text accessible', () => {
    mockTextOverflow()
    const jd = `岗位职责：${'负责后端服务开发、排查和维护。'.repeat(12)}\nJD 末尾`
    const reason = `评分依据：${'服务端经验与岗位要求需要逐项核对。'.repeat(12)}\n理由末尾`
    showJob({ jd, score_reason: reason })

    const jdToggle = screen.getByRole('button', { name: '展开JD摘要全文' })
    const reasonToggle = screen.getByRole('button', { name: '展开评分理由全文' })
    const jdText = document.getElementById(jdToggle.getAttribute('aria-controls')!)!
    const reasonText = document.getElementById(reasonToggle.getAttribute('aria-controls')!)!
    expect(jdToggle.getAttribute('aria-expanded')).toBe('false')
    expect(jdText.className).toContain('line-clamp-6')
    expect(jdText.textContent).toBe(jd)
    expect(reasonText.textContent).toBe(reason)

    fireEvent.click(jdToggle)
    expect(screen.getByRole('button', { name: '收起JD摘要全文' }).getAttribute('aria-expanded')).toBe('true')
    expect(jdText.className).not.toContain('line-clamp-6')
    expect(reasonToggle.getAttribute('aria-expanded')).toBe('false')
    expect(reasonText.className).toContain('line-clamp-6')

    fireEvent.click(reasonToggle)
    expect(screen.getByRole('button', { name: '收起评分理由全文' }).getAttribute('aria-expanded')).toBe('true')
    expect(reasonText.className).not.toContain('line-clamp-6')
    fireEvent.click(screen.getByRole('button', { name: '收起JD摘要全文' }))
    expect(jdText.className).toContain('line-clamp-6')
  })

  it('does not show expansion controls for short or empty text', () => {
    mockTextOverflow()
    showJob({ jd: '负责API', greeting: '', score_reason: '简短理由' })
    expect(screen.queryByRole('button', { name: /JD摘要全文|招呼语全文|评分理由全文/ })).toBeNull()
    expect(screen.getByText('未生成')).toBeTruthy()
  })
})
