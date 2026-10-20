import { describe, it, expect } from 'vitest'
import {
  cn,
  formatCurrency,
  formatNumber,
  formatPercent,
  formatScore,
  formatTimestamp,
  getConfidenceColor,
  getConfidenceTextColor,
  getRiskColor,
  getRiskTextColor,
  getStatusColor,
  getAgentColor,
  getAgentDotColor,
  truncate,
} from '@/lib/utils'

describe('cn', () => {
  it('merges class names', () => {
    expect(cn('foo', 'bar')).toBe('foo bar')
  })

  it('handles conditional classes', () => {
    expect(cn('foo', false && 'bar', 'baz')).toBe('foo baz')
  })

  it('resolves Tailwind conflicts', () => {
    expect(cn('p-2', 'p-4')).toBe('p-4')
  })
})

describe('formatCurrency', () => {
  it('formats zero', () => {
    expect(formatCurrency(0)).toBe('$0')
  })

  it('formats whole numbers', () => {
    expect(formatCurrency(1234)).toBe('$1,234')
  })

  it('formats large numbers', () => {
    expect(formatCurrency(1000000)).toBe('$1,000,000')
  })

  it('rounds decimals', () => {
    expect(formatCurrency(99.99)).toBe('$100')
  })
})

describe('formatNumber', () => {
  it('formats small numbers', () => {
    expect(formatNumber(42)).toBe('42')
  })

  it('formats numbers with commas', () => {
    expect(formatNumber(1234567)).toBe('1,234,567')
  })
})

describe('formatPercent', () => {
  it('formats 0', () => {
    expect(formatPercent(0)).toBe('0%')
  })

  it('formats decimal to percent', () => {
    expect(formatPercent(0.85)).toBe('85%')
  })

  it('formats 1.0', () => {
    expect(formatPercent(1.0)).toBe('100%')
  })
})

describe('formatScore', () => {
  it('formats to 2 decimal places', () => {
    expect(formatScore(0.95)).toBe('0.95')
  })

  it('pads single decimal', () => {
    expect(formatScore(0.5)).toBe('0.50')
  })
})

describe('formatTimestamp', () => {
  it('returns "Just now" for recent timestamps', () => {
    const now = new Date()
    expect(formatTimestamp(now)).toBe('Just now')
  })

  it('returns minutes ago', () => {
    const d = new Date(Date.now() - 5 * 60000)
    expect(formatTimestamp(d)).toBe('5m ago')
  })

  it('returns hours ago', () => {
    const d = new Date(Date.now() - 3 * 3600000)
    expect(formatTimestamp(d)).toBe('3h ago')
  })

  it('returns days ago', () => {
    const d = new Date(Date.now() - 2 * 86400000)
    expect(formatTimestamp(d)).toBe('2d ago')
  })

  it('handles string input', () => {
    const d = new Date(Date.now() - 60000)
    expect(formatTimestamp(d.toISOString())).toBe('1m ago')
  })
})

describe('getConfidenceColor', () => {
  it('returns high for >= 0.8', () => {
    expect(getConfidenceColor(0.9)).toBe('confidence-high')
    expect(getConfidenceColor(0.8)).toBe('confidence-high')
  })

  it('returns medium for >= 0.5', () => {
    expect(getConfidenceColor(0.7)).toBe('confidence-medium')
    expect(getConfidenceColor(0.5)).toBe('confidence-medium')
  })

  it('returns low for < 0.5', () => {
    expect(getConfidenceColor(0.3)).toBe('confidence-low')
    expect(getConfidenceColor(0)).toBe('confidence-low')
  })
})

describe('getConfidenceTextColor', () => {
  it('returns correct text colors', () => {
    expect(getConfidenceTextColor(0.9)).toBe('text-success')
    expect(getConfidenceTextColor(0.6)).toBe('text-warning')
    expect(getConfidenceTextColor(0.2)).toBe('text-danger')
  })
})

describe('getRiskColor', () => {
  it('returns correct bg colors', () => {
    expect(getRiskColor(0.1)).toBe('bg-success')
    expect(getRiskColor(0.5)).toBe('bg-warning')
    expect(getRiskColor(0.8)).toBe('bg-danger')
  })
})

describe('getRiskTextColor', () => {
  it('returns correct text colors', () => {
    expect(getRiskTextColor(0.1)).toBe('text-success')
    expect(getRiskTextColor(0.5)).toBe('text-warning')
    expect(getRiskTextColor(0.8)).toBe('text-danger')
  })
})

describe('getStatusColor', () => {
  it('returns badge for known statuses', () => {
    expect(getStatusColor('active')).toBe('badge-active')
    expect(getStatusColor('pending')).toBe('badge-pending')
    expect(getStatusColor('error')).toBe('badge-error')
  })

  it('returns default for unknown status', () => {
    expect(getStatusColor('unknown')).toBe('badge-pending')
  })
})

describe('getAgentColor', () => {
  it('returns colors for known agents', () => {
    expect(getAgentColor('fraud_detection')).toBe('text-danger')
    expect(getAgentColor('inventory_management')).toBe('text-info')
    expect(getAgentColor('price_optimization')).toBe('text-warning')
  })

  it('returns default for unknown agent', () => {
    expect(getAgentColor('unknown_agent')).toBe('text-primary')
  })
})

describe('getAgentDotColor', () => {
  it('returns dot colors for known agents', () => {
    expect(getAgentDotColor('fraud_detection')).toBe('bg-danger')
    expect(getAgentDotColor('cart_recovery')).toBe('bg-success')
  })
})

describe('truncate', () => {
  it('returns string if shorter than limit', () => {
    expect(truncate('hello', 10)).toBe('hello')
  })

  it('truncates and adds ellipsis', () => {
    expect(truncate('hello world', 5)).toBe('hello...')
  })

  it('handles exact length', () => {
    expect(truncate('hello', 5)).toBe('hello')
  })
})
