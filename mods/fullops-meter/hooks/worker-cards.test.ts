import { describe, expect, test } from 'claude-code/testing'

import { fit, railWidth } from './worker-cards'

describe('worker card layout', () => {
  test('a key longer than its room is cut with an ellipsis', () => {
    expect(fit('SAR-SESSION-PEER-001-DEV-FIX', 12)).toBe('SAR-SESSION…')
    expect(fit('K1', 12)).toBe('K1')
    expect(fit('K12', 1)).toBe('…')
    expect(fit('K1', 0)).toBe('')
  })

  test('the full rail needs 50 cells, so a narrower card falls back to icons', () => {
    expect(railWidth(['explore', 'build', 'verify', 'report'])).toBe(50)
  })
})
