import { describe, expect, it } from 'vitest'
import { commuteDescription, commuteLabel, safeCommuteSourceUrl } from './commute'

describe('commute estimates', () => {
  it('keeps saved time only estimates while marking distance unverified', () => {
    const job = { commute_origin: '示例站', commute_minutes: 42, commute_mode: '地铁', commute_checked_at: '2026-10-01' }
    expect(commuteLabel(job)).toBe('约 42 分钟')
    expect(commuteDescription(job)).toBe('单程通勤：从示例站，距离待核实 · 42 分钟（地铁，地图估算，核于 2026-10-01）')
  })

  it('shows route distance independently of time', () => {
    const job = { commute_origin: '示例站', commute_distance_m: 12345, commute_minutes: 42 }
    expect(commuteLabel(job)).toBe('约 12.3 公里 · 42 分钟')
    expect(commuteDescription({ commute_origin: '示例站', commute_distance_m: 12345 })).toContain('12.3 公里 · 时间待核实')
    expect(commuteLabel({ commute_origin: '示例站', commute_distance_m: 0 })).toBe('约 0 公里')
    expect(commuteLabel({ commute_origin: '示例站', commute_distance_m: 49 })).toBe('约 <0.1 公里')
  })

  it('rejects invalid metrics and requires an origin', () => {
    for (const distance of [-1, Number.NaN, Number.POSITIVE_INFINITY, 1.5]) {
      expect(commuteLabel({ commute_origin: '示例站', commute_distance_m: distance })).toBe('通勤待核实')
    }
    expect(commuteLabel({ commute_origin: '示例站', commute_minutes: 60.5 })).toBe('通勤待核实')
    expect(commuteLabel({ commute_distance_m: 1200, commute_minutes: 42 })).toBe('通勤待核实')
    expect(commuteDescription({ commute_origin: '示例站' })).toBe('单程通勤：待核实，尚无地图估算')
  })
})

describe('original route links', () => {
  it('accepts only allowed Amap route pages and public route parameters', () => {
    const source = 'https://uri.amap.com/navigation?from%5Bname%5D=A&to%5Blnglat%5D=116.1%2C39.1&mode=bus'
    expect(safeCommuteSourceUrl(source)).toBe(source)
    expect(safeCommuteSourceUrl('https://www.amap.com/?r=abc')).toBe('https://www.amap.com/?r=abc')
    expect(safeCommuteSourceUrl('https://ditu.amap.com/dir?from=A&to=B')).toBe('https://ditu.amap.com/dir?from=A&to=B')
  })

  it('rejects unsafe hosts, paths, fragments, credentials and extra query keys', () => {
    for (const source of [
      'javascript:alert(1)', 'http://www.amap.com/?r=abc', 'https://evil.example/?r=abc',
      'https://www.amap.com.evil.example/?r=abc', 'https://user@www.amap.com/?r=abc',
      'https://www.amap.com:8443/?r=abc', 'https://www.amap.com/route?r=abc',
      'https://www.amap.com:443/?r=abc', 'https://www.amap.com/?from',
      ' https://www.amap.com/?r=abc', 'https://www.amap.com/?r=a\nb',
      'https://uri.amap.com/navigation?key=secret', 'https://ditu.amap.com/dir?token=secret',
      'https://www.amap.com/?r=abc#section',
    ]) {
      expect(safeCommuteSourceUrl(source)).toBeNull()
    }
  })
})
