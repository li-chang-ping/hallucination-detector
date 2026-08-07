import {
  categoryChangeEntries,
  categorySnapshotStatus,
  formatCategoryMismatches,
  percent,
  statusText,
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
})
