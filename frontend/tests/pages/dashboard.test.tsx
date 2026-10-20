import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import './mocks'
import { useApprovals, useAgentStatus, useHealth } from '@/lib/hooks'
import type { ApprovalAction, AgentStatus } from '@/lib/api'
import DashboardPage from '@/app/page'

vi.mock('@/components/layout/Shell', () => ({
  default: ({ children, title }: { children: React.ReactNode; title?: string }) => (
    <div data-testid="shell">
      {title && <h1>{title}</h1>}
      {children}
    </div>
  ),
}))

function approval(partial: Partial<ApprovalAction> = {}): ApprovalAction {
  return {
    id: 'ORD-0000',
    agent: 'FraudAgent',
    action_type: 'escalate',
    status: 'pending',
    risk_level: 'medium',
    confidence_score: 0.5,
    created_at: '2026-08-15T00:00:00Z',
    expires_at: null,
    requires_hitl: true,
    shadow_mode: true,
    payload: {},
    evidence: {},
    impact: {},
    reviewed_by: null,
    reviewed_at: null,
    rejection_reason: null,
    operator_notes: null,
    ...partial,
  }
}

function agent(p: Partial<AgentStatus> = {}): AgentStatus {
  return {
    agent_id: 'FraudAgent',
    status: 'active',
    streak: 3,
    autonomy_level: 'supervised',
    total_decisions: 100,
    total_approvals: 80,
    total_rejections: 20,
    avg_confidence: 0.9,
    ...p,
  }
}

describe('DashboardPage', () => {
  it('renders page title', () => {
    render(<DashboardPage />)
    expect(screen.getByText('Command Center')).toBeDefined()
  })

  it('renders metric cards', () => {
    render(<DashboardPage />)
    expect(screen.getByText('Financial Impact')).toBeDefined()
    expect(screen.getByText('Decisions Made')).toBeDefined()
    expect(screen.getByText('Pending Reviews')).toBeDefined()
    expect(screen.getByText('Flagged Orders')).toBeDefined()
  })

  it('renders revenue value', () => {
    render(<DashboardPage />)
    expect(screen.getByText('$124,892.40')).toBeDefined()
  })

  it('renders pending approvals section', () => {
    render(<DashboardPage />)
    expect(screen.getByText('Pending Approvals')).toBeDefined()
  })

  it('renders agent fleet status', () => {
    render(<DashboardPage />)
    expect(screen.getByText('Agent Fleet Status')).toBeDefined()
  })

  it('renders system health card', () => {
    render(<DashboardPage />)
    expect(screen.getByText('System Health')).toBeDefined()
    expect(screen.getByText('WebSocket Status')).toBeDefined()
  })

  it('renders backend info section', () => {
    render(<DashboardPage />)
    expect(screen.getByText('Backend')).toBeDefined()
  })

  it('renders footer', () => {
    render(<DashboardPage />)
    expect(screen.getByText(/All Systems Operational/)).toBeDefined()
  })

  it('renders empty state when no approvals backend data', () => {
    render(<DashboardPage />)
    expect(screen.getByText(/No decisions awaiting review/)).toBeDefined()
  })

  it('renders populated decision table with pagination', () => {
    vi.mocked(useApprovals).mockReturnValue({
      data: [
        approval({ id: 'ORD-1001', risk_level: 'critical', confidence_score: 0.93, impact: { financial_impact: 8500.5 } }),
        approval({ id: 'ORD-1002', risk_level: 'high', confidence_score: 0.8, impact: { financial_impact: 3200 } }),
        approval({ id: 'ORD-1003', risk_level: 'medium', confidence_score: 0.6, payload: { financial_impact: 950.25 } }),
        approval({ id: 'ORD-1004', risk_level: 'low', confidence_score: 0.2 }),
        approval({ id: 'ORD-1005', risk_level: 'high', confidence_score: 0.55, impact: { financial_impact: 120 } }),
        approval({ id: 'ORD-1006', risk_level: 'medium', confidence_score: 0.3 }),
      ],
      isLoading: false,
    } as any)
    render(<DashboardPage />)

    expect(screen.getByText('ORD-1001')).toBeDefined()
    expect(screen.getByText('ORD-1004')).toBeDefined()
    expect(screen.queryByText('ORD-1005')).toBeNull()
    expect(screen.getByText('Showing 4 of 6 pending orders')).toBeDefined()
    expect(screen.getByText('$8,500.50')).toBeDefined()
    expect(screen.getByText('$0.00')).toBeDefined()

    const prev = screen.getByRole('button', { name: 'Previous page' }) as HTMLButtonElement
    const next = screen.getByRole('button', { name: 'Next page' }) as HTMLButtonElement
    expect(prev.disabled).toBe(true)
    expect(next.disabled).toBe(false)

    fireEvent.click(next)
    expect(screen.getByText('Showing 2 of 6 pending orders')).toBeDefined()
    expect(screen.queryByText('ORD-1001')).toBeNull()
    expect(screen.getByText('ORD-1005')).toBeDefined()

    fireEvent.click(screen.getByRole('button', { name: 'Previous page' }) as HTMLButtonElement)
    expect(screen.getByText('Showing 4 of 6 pending orders')).toBeDefined()
  })

  it('renders populated agent fleet with display names', () => {
    vi.mocked(useAgentStatus).mockReturnValue({
      data: [
        agent({ agent_id: 'FraudAgent', status: 'active', avg_confidence: 0.94, total_decisions: 1200 }),
        agent({ agent_id: 'fraud_detection', status: 'inactive', avg_confidence: 0.7, total_decisions: 30 }),
        agent({ agent_id: 'AlphaAgent', status: 'active', avg_confidence: 0.5, total_decisions: 5 }),
      ],
      isLoading: false,
    } as any)
    render(<DashboardPage />)

    expect(screen.getByText('Fraud')).toBeDefined()
    expect(screen.getByText(/fraud_detection/)).toBeDefined()
    expect(screen.getByText('AlphaAgent')).toBeDefined()
    expect(screen.getByText('2 Active')).toBeDefined()
    expect(screen.getByText('3 Total')).toBeDefined()
  })

  it('renders backend dependencies and degraded status', () => {
    vi.mocked(useHealth).mockReturnValue({
      data: {
        status: 'degraded',
        environment: 'staging',
        version_number: '2.5.0',
        dependencies: { database: 'healthy', redis: 'down', task_queue: '4' },
      },
      isLoading: false,
    } as any)
    render(<DashboardPage />)

    expect(screen.getByText('CHECK')).toBeDefined()
    expect(screen.getByText('staging')).toBeDefined()
    expect(screen.getByText('v2.5.0')).toBeDefined()
    expect(screen.getByText('HEALTHY')).toBeDefined()
    expect(screen.getByText('DOWN')).toBeDefined()
    expect(screen.getByText('Task queue depth: 4')).toBeDefined()
    expect(screen.getByText('System Degraded')).toBeDefined()
  })

  it('renders unreachable approvals message when no data', () => {
    vi.mocked(useApprovals).mockReturnValueOnce({ data: undefined, isLoading: false } as any)
    render(<DashboardPage />)
    expect(screen.getByText(/Approvals endpoint is unreachable/)).toBeDefined()
  })
})