import {
  canCancelTask,
  canEvaluateTask,
  categoryChangeEntries,
  categorySnapshotStatus,
  formatCategoryMismatches,
  isDialogCancelled,
  percent,
  statusText,
  taskProgress,
} from '../src/utils'

describe('display utilities', () => {
  it('formats evaluation ratios', () => expect(percent(0.9444)).toBe('94.4%'))
  it('provides Chinese task status', () => expect(statusText.paused).toBe('已暂停'))
  it('formats category mismatch details', () => {
    expect(
      formatCategoryMismatches([
        {
          id: 'h08',
          expected_category: '政策偏差',
          predicted_category: '事实信息编造',
        },
      ]),
    ).toBe('h08（人工：政策偏差；模型：事实信息编造）')
  })
  it('formats category suggestion fields', () => {
    expect(categoryChangeEntries({ prompt_guidance: '优先识别政策条件' })).toEqual([
      ['判定指引', '优先识别政策条件'],
    ])
  })
  it('formats category snapshot status', () => {
    expect(categorySnapshotStatus({ is_active: true, is_archived: false })).toBe('已启用')
    expect(categorySnapshotStatus({ is_active: false, is_archived: true })).toBe('已归档')
  })
  it('recognizes dialog cancellation without hiding real errors', () => {
    expect(isDialogCancelled('cancel')).toBe(true)
    expect(isDialogCancelled('close')).toBe(true)
    expect(isDialogCancelled(new Error('接口失败'))).toBe(false)
  })
  it('keeps task actions aligned with backend terminal states', () => {
    expect(canCancelTask('running')).toBe(true)
    expect(canCancelTask('failed')).toBe(false)
    expect(canEvaluateTask('running')).toBe(false)
    expect(canEvaluateTask('partial')).toBe(true)
  })
  it('returns a safe bounded progress percentage', () => {
    expect(taskProgress(0, 0, 0)).toBe(0)
    expect(taskProgress(4, 2, 1)).toBe(75)
    expect(taskProgress(1, 2, 0)).toBe(100)
  })
})
