import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import './mocks'
import AgentsPage from '@/app/agents/page'

vi.mock('@/components/layout/Shell', () => ({
  default: ({ children, title, actions }: { children: React.ReactNode; title?: string; actions?: React.ReactNode }) => (
    <div data-testid="shell">
      {title && <h1>{title}</h1>}
      {actions && <div data-testid="shell-actions">{actions}</div>}
      {children}
    </div>
  ),
}))

describe('AgentsPage', () => {
  it('renders page title', () => {
    render(<AgentsPage />)
    expect(screen.getByText('Autonomous Agents')).toBeDefined()
  })

  it('renders all 7 agent cards', () => {
    render(<AgentsPage />)
    expect(screen.getByText('Fraud Detection')).toBeDefined()
    expect(screen.getAllByText('Inventory').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Price Optimizer').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('Review Moderator')).toBeDefined()
    expect(screen.getByText('Marketing')).toBeDefined()
    expect(screen.getByText('Cart Recovery')).toBeDefined()
    expect(screen.getByText('Customer Support')).toBeDefined()
  })

  it('renders filter tabs via actions', () => {
    render(<AgentsPage />)
    const actions = screen.getByTestId('shell-actions')
    expect(within(actions).getByText('All Agents')).toBeDefined()
    expect(within(actions).getByText('Shadow')).toBeDefined()
    expect(within(actions).getByText('Supervised')).toBeDefined()
    expect(within(actions).getByText('Autonomous')).toBeDefined()
  })

  it('filters agents when Shadow tab is clicked', () => {
    render(<AgentsPage />)
    const actions = screen.getByTestId('shell-actions')
    fireEvent.click(within(actions).getByText('Shadow'))
    expect(screen.getByText('Price Optimizer')).toBeDefined()
    expect(screen.getByText('Review Moderator')).toBeDefined()
    expect(screen.getByText('Marketing')).toBeDefined()
    expect(screen.getByText('Customer Support')).toBeDefined()
    expect(screen.queryByText('Fraud Detection')).toBeNull()
  })

  it('filters agents when Supervised tab is clicked', () => {
    render(<AgentsPage />)
    const actions = screen.getByTestId('shell-actions')
    fireEvent.click(within(actions).getByText('Supervised'))
    expect(screen.getByText('Fraud Detection')).toBeDefined()
    expect(screen.getAllByText('Inventory').length).toBeGreaterThanOrEqual(1)
    expect(screen.queryByText('Price Optimizer')).toBeNull()
  })

  it('renders summary stats cards', () => {
    render(<AgentsPage />)
    expect(screen.getByText('Total Agents')).toBeDefined()
    expect(screen.getAllByText('Autonomous').length).toBeGreaterThanOrEqual(2)
    expect(screen.getAllByText('Supervised').length).toBeGreaterThanOrEqual(2)
    expect(screen.getAllByText('Shadow').length).toBeGreaterThanOrEqual(2)
  })
})
