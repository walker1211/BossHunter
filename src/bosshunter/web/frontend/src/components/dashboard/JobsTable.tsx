import { Fragment, useEffect, useId, useRef, useState } from 'react'
import { OutsourcingBadge } from '@/components/jobs/OutsourcingBadge'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Ban, CheckCircle2, ChevronDown, ChevronUp, ExternalLink, Trash2 } from 'lucide-react'
import { getStatusLabel } from '@/lib/status'
import { PLATFORM_SHORT_LABELS } from '@/lib/platforms'
import { safeCompanyProfileUrl, workScheduleDescription, workScheduleLabel, workScheduleSourceLabel } from '@/lib/workSchedule'
import { commuteDescription, commuteLabel, safeCommuteSourceUrl } from '@/lib/commute'
import type { Job } from '@/hooks/useDashboard'
import type { JobSortKey, JobSortOrder } from '@/hooks/useJobSearch'
import { InterviewPreparation } from '@/components/jobs/InterviewPreparation'

interface JobsTableProps {
  jobs: Job[]
  page: number
  pageSize: number
  total: number
  onPageChange: (page: number) => void
  selectedIds: string[]
  onToggleSelected: (id: string) => void
  onSoftDelete?: (job: Job) => void
  onMarkManuallySent?: (job: Job) => void
  onStatusChange?: (job: Job, status: string) => void
  onBlockCompany?: (job: Job) => void
  blockedCompanies?: string[]
  blockingJobId?: string | null
  loading?: boolean
  sortBy: JobSortKey
  sortOrder: JobSortOrder
  onSortChange: (sortBy: JobSortKey) => void
}

function safeJobUrl(job: Job): string | null {
  const platform = job.source_platform || 'boss'
  if (platform !== 'boss' && platform !== 'zhilian' && platform !== '51job' && platform !== 'liepin') return null
  try {
    const parsed = platform === 'boss'
      ? new URL(job.url || '', 'https://www.zhipin.com')
      : new URL(job.url || '')
    if (parsed.protocol !== 'https:') return null
    const rootDomain = platform === 'boss'
      ? 'zhipin.com'
      : platform === 'zhilian'
        ? 'zhaopin.com'
        : platform === '51job'
          ? '51job.com'
          : 'liepin.com'
    if (parsed.hostname !== rootDomain && !parsed.hostname.endsWith(`.${rootDomain}`)) return null
    return parsed.toString()
  } catch {
    return null
  }
}

function statusVariant(status: string) {
  const variants = new Set([
    'pending',
    'scored',
    'filtered',
    'ready',
    'approved',
    'skipped',
    'sent',
    'replied',
    'resume_sent',
    'needs_resume',
    'follow_up_sent',
    'rejected',
    'error',
  ])
  return variants.has(status) ? status : 'default'
}

function ExpandableJobText({ label, value, fallback }: { label: string, value?: string | null, fallback: string }) {
  const [expanded, setExpanded] = useState(false)
  const [overflowing, setOverflowing] = useState(false)
  const textRef = useRef<HTMLParagraphElement>(null)
  const textId = useId()
  const hasText = Boolean(value?.trim())

  useEffect(() => {
    setExpanded(false)
  }, [value])

  useEffect(() => {
    if (!hasText || expanded) {
      if (!hasText) setOverflowing(false)
      return
    }
    const element = textRef.current
    if (!element) return
    const measure = () => setOverflowing(element.scrollHeight > element.clientHeight + 1)
    measure()

    if (typeof ResizeObserver !== 'undefined') {
      const observer = new ResizeObserver(measure)
      observer.observe(element)
      return () => observer.disconnect()
    }
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [expanded, hasText, value])

  return (
    <div className="min-w-0 rounded-2xl border border-card-border bg-card p-4">
      <p className="mb-2 text-xs font-black text-primary">{label}</p>
      <p
        id={textId}
        ref={textRef}
        className={`${expanded ? '' : 'line-clamp-6'} whitespace-pre-wrap break-words [overflow-wrap:anywhere] leading-6 text-muted`}
        title={overflowing && !expanded ? '点击下方“展开全文”查看完整内容' : undefined}
      >{hasText ? value : fallback}</p>
      {overflowing && (
        <button
          type="button"
          aria-label={`${expanded ? '收起' : '展开'}${label}全文`}
          aria-expanded={expanded}
          aria-controls={textId}
          onClick={() => setExpanded(!expanded)}
          className="mt-2 rounded text-xs font-bold text-primary underline underline-offset-2 hover:text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >{expanded ? '收起' : '展开全文'}</button>
      )}
    </div>
  )
}

export function JobsTable({ jobs, page, pageSize, total, onPageChange, selectedIds, onToggleSelected, onSoftDelete, onMarkManuallySent, onStatusChange, onBlockCompany, blockedCompanies = [], blockingJobId = null, loading = false, sortBy, sortOrder, onSortChange }: JobsTableProps) {
  const [expanded, setExpanded] = useState<string | null>(null)
  const [pageInput, setPageInput] = useState(String(page + 1))
  const totalPages = Math.ceil(total / pageSize)
  const hasActions = Boolean(onSoftDelete || onMarkManuallySent || onStatusChange || onBlockCompany)

  useEffect(() => {
    setPageInput(String(page + 1))
  }, [page])

  const jumpToPage = () => {
    const requested = Number.parseInt(pageInput, 10)
    if (!Number.isFinite(requested) || totalPages < 1) {
      setPageInput(String(page + 1))
      return
    }
    onPageChange(Math.min(totalPages - 1, Math.max(0, requested - 1)))
  }

  const getScoreColor = (score: number) => {
    if (score >= 80) return 'text-success'
    if (score >= 60) return 'text-primary'
    return 'text-muted'
  }

  const timeAgo = (dateStr: string) => {
    if (!dateStr) return ''
    const normalizedDate = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(dateStr)
      ? `${dateStr.replace(' ', 'T')}Z`
      : dateStr
    const timestamp = new Date(normalizedDate).getTime()
    if (Number.isNaN(timestamp)) return ''
    const diff = Date.now() - timestamp
    const hours = Math.floor(diff / 3600000)
    if (hours < 1) return '刚刚'
    if (hours < 24) return `${hours}h 前`
    return `${Math.floor(hours / 24)}d 前`
  }

  const sortableHeader = (label: string, key: JobSortKey) => (
    <button
      type="button"
      onClick={() => onSortChange(key)}
      className="inline-flex items-center gap-1 font-bold hover:text-primary"
      title={`按${label}排序`}
    >
      {label}<span className="text-[10px]">{sortBy === key ? (sortOrder === 'asc' ? '↑' : '↓') : '↕'}</span>
    </button>
  )

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>岗位列表</CardTitle>
        <span className="text-xs text-muted">{total} 条记录</span>
      </CardHeader>
      <CardContent className="p-0">
        <div className="overflow-x-auto [container-type:inline-size]">
          <table className="w-full text-sm">
            <thead>
              <tr className="whitespace-nowrap border-b border-card-border bg-secondary text-xs text-muted">
                <th className="w-10 px-3 py-3 text-center font-bold">选</th>
                <th className="px-4 py-3 text-left font-bold">公司</th>
                <th className="px-4 py-3 text-left font-bold">职位</th>
                <th className="px-4 py-3 text-left font-bold">城市 / 通勤</th>
                <th className="px-4 py-3 text-left font-bold">休息安排</th>
                <th className="px-4 py-3 text-left">{sortableHeader('薪资', 'salary')}</th>
                <th className="px-4 py-3 text-left">{sortableHeader('学历 / 招聘类型', 'education')}</th>
                <th className="px-4 py-3 text-left">{sortableHeader('评分', 'score')}</th>
                <th className="px-4 py-3 text-left">{sortableHeader('状态', 'status')}</th>
                <th className="px-4 py-3 text-left">{sortableHeader('招聘者活跃', 'hr_active')}</th>
                <th className="px-4 py-3 text-left" title="本地首次收录时间，并非招聘平台的发布时间">{sortableHeader('收录时间', 'created_at')}</th>
                {hasActions && <th className="min-w-[210px] px-3 py-3 text-center font-bold">操作</th>}
              </tr>
            </thead>
            <tbody>
              {jobs.map(job => {
                const isExpanded = expanded === job.id
                const isExternalPlatform = job.source_platform === 'zhilian' || job.source_platform === '51job' || job.source_platform === 'liepin'
                const jobUrl = safeJobUrl(job)
                const companyProfileUrl = safeCompanyProfileUrl(job.company_url)
                const commuteSourceUrl = safeCommuteSourceUrl(job.commute_source_url)
                const alreadySent = ['sent', 'replied', 'resume_sent', 'needs_resume', 'follow_up_sent'].includes(job.status)
                const company = (job.company || '').trim()
                const blockedRule = blockedCompanies.find(rule => rule.trim() && company.toLowerCase().includes(rule.trim().toLowerCase()))
                return (
                  <Fragment key={job.id}>
                    <tr
                      className="cursor-pointer border-b border-card-border bg-card transition-colors hover:bg-surface"
                      onClick={() => setExpanded(isExpanded ? null : job.id)}
                    >
                      <td className="px-3 py-3 text-center" onClick={event => event.stopPropagation()}>
                        <input
                          type="checkbox"
                          checked={selectedIds.includes(job.id)}
                          onChange={() => onToggleSelected(job.id)}
                          aria-label={`选择 ${job.company} ${job.title}`}
                          className="h-4 w-4 accent-primary"
                        />
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            className="max-w-[160px] truncate rounded text-left font-black text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
                            aria-expanded={isExpanded}
                            aria-controls={isExpanded ? `job-details-${job.id}` : undefined}
                            aria-label={`${isExpanded ? '收起' : '展开'} ${job.company} ${job.title} 详情`}
                            onClick={event => {
                              event.stopPropagation()
                              setExpanded(isExpanded ? null : job.id)
                            }}
                          >{job.company}</button>
                          <span className={`rounded-full px-2 py-0.5 text-[10px] font-black ${job.source_platform === 'boss' || !job.source_platform ? 'bg-secondary text-primary' : 'bg-info-soft text-info'}`}>
                            {PLATFORM_SHORT_LABELS[job.source_platform || 'boss'] || 'BOSS'}
                          </span>
                          <OutsourcingBadge job={job} />
                          {job.company_size && (
                            <span className="rounded-full bg-surface px-2 py-0.5 text-[10px] font-bold text-muted">{job.company_size}</span>
                          )}
                        </div>
                      </td>
                      <td className="max-w-[220px] truncate px-4 py-3 font-bold text-foreground">{job.title}</td>
                      <td className="px-4 py-3 text-muted">
                        <div>{job.city || '未识别'}</div>
                        <div className="mt-1 whitespace-nowrap text-xs" title={commuteDescription(job)}>{commuteLabel(job)}</div>
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-xs text-muted" title={`信息来源：${workScheduleSourceLabel(job.work_schedule_source)}；原文依据：${job.work_schedule_evidence || '未记录'}；尚未向招聘方核实`}>{workScheduleLabel(job.work_schedule, job.work_schedule_source)}</td>
                      <td className="px-4 py-3 text-muted">{job.salary || '-'}</td>
                      <td className="px-4 py-3 text-xs">
                        <div className="font-bold text-foreground">{job.education || '学历未识别'}</div>
                        <div className="mt-1 text-muted">职位类型：{job.employment_type === 'internship' ? '实习' : job.employment_type === 'full_time' ? '全职' : job.employment_type === 'part_time' ? '兼职' : '待核实'}</div>
                        {job.employment_review && <div className="mt-1 text-amber-600">{job.employment_review}</div>}
                        <div className="mt-1 text-muted">{job.recruitment_type === 'campus' ? '校招' : job.recruitment_type === 'experienced' ? '社招' : '类型未识别'}</div>
                      </td>
                      <td className="px-4 py-3">
                        {job.status === 'filtered' && job.score === 0 && job.score_reason?.startsWith('预筛不通过:')
                          ? <span className="text-xs font-bold text-muted" title="命中预筛规则，尚未调用 AI 评分">预筛未评</span>
                          : <span className={`font-mono font-black ${getScoreColor(job.score)}`}>{job.score || '-'}</span>}
                      </td>
                      <td className="px-4 py-3">
                        <Badge className="whitespace-nowrap" variant={statusVariant(job.status) as any}>{getStatusLabel(job.status)}</Badge>
                      </td>
                      <td className="px-4 py-3">
                        <Badge className="whitespace-nowrap" title="采集时记录的 HR 活跃状态，不代表实时状态">
                          {job.hr_active?.trim() || '活跃度未知'}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 text-xs text-muted">
                        <div className="flex items-center gap-2">
                          {timeAgo(job.created_at)}
                          {isExpanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                        </div>
                      </td>
                      {hasActions && (
                        <td className="px-3 py-3" onClick={event => event.stopPropagation()}>
                          <div className="flex flex-wrap items-center justify-center gap-1.5">
                            {isExternalPlatform && jobUrl && (
                              <a href={jobUrl} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 rounded-lg border border-card-border px-2 py-1.5 text-[11px] font-bold text-primary hover:bg-secondary">
                                <ExternalLink className="h-3.5 w-3.5" />打开平台
                              </a>
                            )}
                            {isExternalPlatform && !jobUrl && (
                              <span className="rounded-lg bg-warning-soft px-2 py-1.5 text-[11px] font-bold text-warning">链接不可用</span>
                            )}
                            {!isExternalPlatform && jobUrl && (
                              <a href={jobUrl} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 rounded-lg border border-card-border px-2 py-1.5 text-[11px] font-bold text-primary hover:bg-secondary">
                                <ExternalLink className="h-3.5 w-3.5" />跳转岗位
                              </a>
                            )}
                            {isExternalPlatform && onMarkManuallySent && (
                              <button
                                type="button"
                                disabled={alreadySent}
                                onClick={() => onMarkManuallySent(job)}
                                className="inline-flex items-center gap-1 rounded-lg bg-primary px-2 py-1.5 text-[11px] font-bold text-primary-foreground hover:opacity-90 disabled:bg-success-soft disabled:text-success disabled:opacity-100"
                              >
                                <CheckCircle2 className="h-3.5 w-3.5" />{alreadySent ? '已发送' : '我已发送'}
                              </button>
                            )}
                            {onSoftDelete && (
                              <button type="button" onClick={() => onSoftDelete(job)} className="rounded-lg p-2 text-muted hover:bg-danger-soft hover:text-danger" aria-label={`将 ${job.company} ${job.title} 移入回收站`}>
                                <Trash2 className="h-4 w-4" />
                              </button>
                            )}
                            {onBlockCompany && (
                              <button
                                type="button"
                                disabled={!company || Boolean(blockedRule) || Boolean(blockingJobId)}
                                onClick={() => onBlockCompany(job)}
                                aria-label={`屏蔽公司 ${company || '公司名缺失'}`}
                                title={blockedRule ? `已被“${blockedRule}”屏蔽，可在配置中解除` : company ? '预览后将公司加入屏蔽名单' : '缺少公司名称，无法屏蔽'}
                                className="inline-flex items-center gap-1 rounded-lg border border-card-border px-2 py-1.5 text-[11px] font-bold text-muted hover:bg-danger-soft hover:text-danger disabled:cursor-not-allowed disabled:opacity-50"
                              >
                                <Ban className="h-3.5 w-3.5" />{blockingJobId === job.id ? '处理中…' : blockedRule ? '已屏蔽' : '屏蔽公司'}
                              </button>
                            )}
                            {onStatusChange && !alreadySent && (
                              <select
                                defaultValue=""
                                aria-label={`修改 ${job.company} ${job.title} 状态`}
                                onChange={event => {
                                  const status = event.target.value
                                  if (status) onStatusChange(job, status)
                                  event.currentTarget.value = ''
                                }}
                                className="rounded-lg border border-card-border bg-card px-2 py-1.5 text-[11px] font-bold text-foreground"
                              >
                                <option value="">修改状态</option>
                                <option value="ready">待确认</option>
                                <option value="filtered">已过滤</option>
                                <option value="skipped">已跳过</option>
                                <option value="rejected">已拒绝</option>
                              </select>
                            )}
                          </div>
                        </td>
                      )}
                    </tr>
                    {isExpanded && (
                      <tr className="border-b border-card-border bg-surface">
                        <td id={`job-details-${job.id}`} colSpan={hasActions ? 12 : 11} className="px-6 py-4">
                          <div className="sticky left-6 w-[calc(100cqw-3rem)] max-w-full min-w-0">
                            <div className="mb-4 max-w-2xl">
                              <InterviewPreparation key={job.id} job={job} />
                            </div>
                            <div className="grid gap-4 text-sm [grid-template-columns:repeat(auto-fit,minmax(min(100%,18rem),1fr))]">
                              <ExpandableJobText label="JD摘要" value={job.jd} fallback="无" />
                              <ExpandableJobText label="招呼语" value={job.greeting} fallback="未生成" />
                              <ExpandableJobText label="评分理由" value={job.score_reason} fallback="无" />
                            </div>
                            <div className="mt-3 grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(min(100%,22rem),1fr))]">
                              <div className="min-w-0 rounded-2xl border border-card-border bg-card p-4">
                                <p className="text-xs font-black text-primary">休息安排及依据</p>
                                <p className="mt-2 break-words [overflow-wrap:anywhere] leading-6 text-muted">{workScheduleDescription(job.work_schedule, job.work_schedule_source)}</p>
                                <p className="mt-1 whitespace-pre-wrap break-words [overflow-wrap:anywhere] leading-6 text-muted">原文依据：{job.work_schedule_evidence || '未记录'}</p>
                                {companyProfileUrl && (
                                  <a href={companyProfileUrl} target="_blank" rel="noopener noreferrer" className="mt-2 inline-block font-bold text-primary underline">原公司页链接</a>
                                )}
                              </div>
                              <div className="min-w-0 rounded-2xl border border-card-border bg-card p-4">
                                <p className="text-xs font-black text-primary">办公地点与通勤</p>
                                <p className="mt-2 break-words [overflow-wrap:anywhere] leading-6 text-muted">办公地点：{job.work_location || '未采集'}</p>
                                <p className="mt-1 break-words [overflow-wrap:anywhere] leading-6 text-muted">{commuteDescription(job)}</p>
                                {commuteSourceUrl && <a href={commuteSourceUrl} target="_blank" rel="noopener noreferrer" className="mt-2 inline-block rounded text-primary underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary">查看原地图路线</a>}
                              </div>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
              {!jobs.length && (
                <tr>
                  <td colSpan={hasActions ? 12 : 11} className="px-4 py-10 text-center text-sm text-muted">
                    {loading ? '正在读取岗位…' : '没有符合当前条件的岗位'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {totalPages > 0 && (
          <div className="flex flex-wrap items-center justify-center gap-3 border-t border-card-border px-4 py-3 text-xs">
            <button
              onClick={() => onPageChange(0)}
              disabled={page === 0}
              className="font-bold text-muted transition hover:text-foreground disabled:opacity-30"
            >
              首页
            </button>
            <button
              onClick={() => onPageChange(Math.max(0, page - 1))}
              disabled={page === 0}
              className="font-bold text-muted transition hover:text-foreground disabled:opacity-30"
            >
              上一页
            </button>
            <label className="flex items-center gap-1 text-muted">
              第
              <input
                type="number"
                min={1}
                max={Math.max(1, totalPages)}
                value={pageInput}
                onChange={event => setPageInput(event.target.value)}
                onKeyDown={event => { if (event.key === 'Enter') jumpToPage() }}
                onBlur={jumpToPage}
                aria-label="跳转页码"
                className="w-14 rounded-md border border-card-border bg-surface px-2 py-1 text-center text-foreground outline-none focus:border-primary"
              />
              页 / {totalPages} 页
            </label>
            <button
              onClick={() => onPageChange(Math.min(totalPages - 1, page + 1))}
              disabled={page >= totalPages - 1}
              className="font-bold text-muted transition hover:text-foreground disabled:opacity-30"
            >
              下一页
            </button>
            <button
              onClick={() => onPageChange(totalPages - 1)}
              disabled={page >= totalPages - 1}
              className="font-bold text-muted transition hover:text-foreground disabled:opacity-30"
            >
              尾页
            </button>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
