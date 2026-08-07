import { percent, statusText } from '../src/utils'

describe('display utilities', () => {
  it('formats evaluation ratios', () => expect(percent(0.9444)).toBe('94.4%'))
  it('provides Chinese task status', () => expect(statusText.paused).toBe('已暂停'))
})
