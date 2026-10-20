import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import './mocks'
import AnalyticsPage from '@/app/analytics/page'

vi.mock('@/components/layout/Shell', () => ({
  default: ({ children, title, actions }: { children: React.ReactNode; title?: string; actions?: React.ReactNode }) => (
    <div data-testid="shell">
      {title && <h1>{title}</h1>}
      {actions && <div data-testid="shell-actions">{actions}</div>}
      {children}
    </div>
  ),
}))

describe('AnalyticsPage', () => {
  it('renders page title', () => {
    render(<AnalyticsPage />)
    expect(screen.getByText('Performance Intelligence')).toBeDefined()
  })

  it('renders metric cards from backend data', () => {
    render(<AnalyticsPage />)
    expect(screen.getByText('FINANCIAL IMPACT')).toBeDefined()
    expect(screen.getByText('$124,892.40')).toBeDefined()
    expect(screen.getByText('DECISIONS MADE')).toBeDefined()
    expect(screen.getByText('14,208')).toBeDefined()
    expect(screen.getByText('APPROVAL RATE')).toBeDefined()
    expect(screen.getByText('82.1%')).toBeDefined()
    expect(screen.getByText('AVG DECISION TIME')).toBeDefined()
    expect(screen.getByText('1.4 min')).toBeDefined()
  })

  it('renders time range filter buttons', () => {
    render(<AnalyticsPage />)
    expect(screen.getByText('30D')).toBeDefined()
    expect(screen.getByText('7D')).toBeDefined()
    expect(screen.getByText('24H')).toBeDefined()
  })

  it('switches time range on click', () => {
    render(<AnalyticsPage />)
    const btn7d = screen.getByText('7D')
    fireEvent.click(btn7d)
    expect(btn7d.className).toContain('bg-primary/15')
  })

  it('renders risk distribution table from backend data', () => {
    render(<AnalyticsPage />)
    expect(screen.getByText('Risk Distribution')).toBeDefined()
    expect(screen.getByText('Critical')).toBeDefined()
    expect(screen.getByText('High')).toBeDefined()
    expect(screen.getByText('Medium')).toBeDefined()
    expect(screen.getByText('Low')).toBeDefined()
  })

  it('renders charts section without fabricating visuals', () => {
    render(<AnalyticsPage />)
    expect(screen.getByText('Charts')).toBeDefined()
    expect(screen.getByText(/Backend returned chart data/)).toBeDefined()
    expect(screen.getByText(/approval_rate_over_time/)).toBeDefined()
    expect(screen.getByText(/volume_by_agent/)).toBeDefined()
    expect(screen.getByText(/decision_time_dist/)).toBeDefined()
  })

  it('renders export button', () => {
    render(<AnalyticsPage />)
    expect(screen.getByText('Export')).toBeDefined()
  })
})