export type WorkSchedule = 'double' | 'alternate' | 'single' | 'unclear' | 'unknown'

export function workScheduleLabel(schedule?: WorkSchedule) {
  switch (schedule) {
    case 'double': return '文案称双休'
    case 'alternate': return '文案称大小周'
    case 'single': return '文案称单休'
    case 'unclear': return '表述冲突'
    default: return '未说明'
  }
}

export function workScheduleDescription(schedule?: WorkSchedule) {
  return schedule && schedule !== 'unknown'
    ? `${workScheduleLabel(schedule)}；尚未向招聘方核实`
    : '职位未说明；待核实'
}
