import { describe, expect, it } from 'vitest'
import { safeCompanyProfileUrl, workScheduleDescription, workScheduleLabel, workScheduleSourceLabel } from './workSchedule'

describe('work schedule claims', () => {
  it('keeps legacy job posting labels', () => {
    expect(workScheduleLabel('double')).toBe('文案称双休')
    expect(workScheduleLabel('single', 'job_posting')).toBe('文案称单休')
    expect(workScheduleSourceLabel('job_posting')).toBe('职位文案')
  })

  it('attributes company page claims without implying verification', () => {
    expect(workScheduleLabel('double', 'company_profile')).toBe('公司页称双休')
    expect(workScheduleLabel('single', 'company_profile')).toBe('公司页称单休')
    expect(workScheduleLabel('alternate', 'company_profile')).toBe('公司页称大小周')
    expect(workScheduleDescription('double', 'company_profile')).toContain('尚未向招聘方核实')
    expect(workScheduleSourceLabel('company_profile')).toBe('公司页（福利/简介）')
  })

  it('keeps unclear and unknown claims conservative', () => {
    expect(workScheduleLabel('unclear', 'company_profile')).toBe('表述冲突')
    expect(workScheduleLabel('unknown', 'company_profile')).toBe('未说明')
    expect(workScheduleDescription('unknown', '')).toContain('尚未向招聘方核实')
    expect(workScheduleSourceLabel('')).toBe('未记录')
    expect(workScheduleLabel('double', 'manual')).toBe('人工记录称双休')
    expect(workScheduleSourceLabel('legacy')).toBe('其他来源（legacy）')
    expect(workScheduleLabel('double', 'legacy')).toBe('来源称双休')
  })
})

describe('company profile URL', () => {
  it('accepts only HTTPS company pages on zhipin.com', () => {
    expect(safeCompanyProfileUrl('https://www.zhipin.com/gongsi/123.html')).toBe('https://www.zhipin.com/gongsi/123.html')
    expect(safeCompanyProfileUrl('https://zhipin.com/gongsi/abc_1-~.html?from=search#details')).toBe('https://www.zhipin.com/gongsi/abc_1-~.html')
    expect(safeCompanyProfileUrl('/gongsi/relative.html?tracking=1')).toBe('https://www.zhipin.com/gongsi/relative.html')
    for (const url of [
      'javascript:alert(1)', 'https://evil.example/gongsi/123',
      'https://zhipin.com.evil.example/gongsi/123', 'https://www.zhipin.com/job_detail/123',
      'https://user@www.zhipin.com/gongsi/123.html', '/gongsi/123',
      'https://m.zhipin.com/gongsi/123.html', 'http://www.zhipin.com/gongsi/123.html',
      'https://www.zhipin.com:8443/gongsi/123.html', 'https://www.zhipin.com/gongsi/job',
      'https://www.zhipin.com/gongsi/123.html/more',
    ]) {
      expect(safeCompanyProfileUrl(url)).toBeNull()
    }
  })
})
