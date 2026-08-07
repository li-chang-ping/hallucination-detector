import { formatCategoryMismatches, percent, statusText } from '../src/utils'

describe('display utilities', () => {
  it('formats evaluation ratios', () => expect(percent(0.9444)).toBe('94.4%'))
  it('provides Chinese task status', () => expect(statusText.paused).toBe('已暂停'))
  it('formats category mismatch details', () => {
    expect(
      formatCategoryMismatches([
        {
          id: 'h08',
          expected_category: '政策与优惠错误',
          predicted_primary_category: '事实信息编造',
          predicted_categories: ['事实信息编造'],
        },
      ]),
    ).toBe('h08（人工：政策与优惠错误；模型：事实信息编造）')
  })
})
