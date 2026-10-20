import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import './mocks'
import { useSettings, useUpdateSettings } from '@/lib/hooks'
import SettingsPage from '@/app/settings/page'

vi.mock('@/components/layout/Shell', () => ({
  default: ({ children, title }: { children: React.ReactNode; title?: string }) => (
    <div data-testid="shell">
      {title && <h1>{title}</h1>}
      {children}
    </div>
  ),
}))

vi.mock('@/components/shared/Toggle', () => ({
  default: ({ enabled, onToggle, label }: { enabled: boolean; onToggle: () => void; label?: string }) => (
    <button
      role="switch"
      aria-checked={enabled}
      aria-label={label}
      onClick={onToggle}
      data-testid={`toggle-${label || 'unknown'}`}
    >
      {enabled ? 'On' : 'Off'}
    </button>
  ),
}))

describe('SettingsPage', () => {
  it('renders page title', () => {
    render(<SettingsPage />)
    expect(screen.getByText('System Settings')).toBeDefined()
  })

  it('renders Automation Behavior section', () => {
    render(<SettingsPage />)
    expect(screen.getByText('Automation Behavior')).toBeDefined()
    expect(screen.getByText('Control how agents operate across the store')).toBeDefined()
  })

  it('renders Risk & Spend Limits section', () => {
    render(<SettingsPage />)
    expect(screen.getByText('Risk & Spend Limits')).toBeDefined()
    expect(screen.getByText('Set caps agents must respect before taking action')).toBeDefined()
  })

  it('renders configuration inputs', () => {
    render(<SettingsPage />)
    expect(screen.getByText('Shadow Mode')).toBeDefined()
    expect(screen.getByText('Fraud Score Threshold')).toBeDefined()
    expect(screen.getByText('Purchase Order Limit')).toBeDefined()
    expect(screen.getByText('Pricing Change Limit (%)')).toBeDefined()
    expect(screen.getByText('Review Sentiment Threshold')).toBeDefined()
  })

  it('hydrates form values from settings', () => {
    render(<SettingsPage />)
    expect((screen.getByText('Fraud Score Threshold').parentElement?.querySelector('input[type="range"]') as HTMLInputElement)?.value).toBe('70')
    expect((screen.getByText('Purchase Order Limit').parentElement?.querySelector('input[type="number"]') as HTMLInputElement)?.value).toBe('1000')
    expect((screen.getByText('Pricing Change Limit (%)').parentElement?.querySelector('input[type="number"]') as HTMLInputElement)?.value).toBe('5')
  })

  it('renders Save Changes button', () => {
    render(<SettingsPage />)
    expect(screen.getByText('Save Changes')).toBeDefined()
  })

  it('renders shadow mode toggle enabled by default', () => {
    render(<SettingsPage />)
    const toggle = screen.getByRole('switch')
    expect(toggle.getAttribute('aria-checked')).toBe('true')
  })

  it('toggles shadow mode state on click', () => {
    render(<SettingsPage />)
    const toggle = screen.getByRole('switch')
    fireEvent.click(toggle)
    expect(toggle.getAttribute('aria-checked')).toBe('false')
  })

  it('renders loading state while settings load', () => {
    vi.mocked(useSettings).mockReturnValueOnce({ data: undefined, isLoading: true } as any)
    render(<SettingsPage />)
    expect(screen.getByText(/Loading current settings from the backend/)).toBeDefined()
  })

  it('renders error banner when settings fail to load', () => {
    vi.mocked(useSettings).mockReturnValueOnce({ data: undefined, isLoading: false, isError: true } as any)
    render(<SettingsPage />)
    expect(screen.getByText(/Failed to load settings\. Showing last known values\./)).toBeDefined()
  })

  it('updates fraud score threshold via range input', () => {
    render(<SettingsPage />)
    const input = screen.getByText('Fraud Score Threshold').parentElement?.querySelector('input[type="range"]') as HTMLInputElement
    fireEvent.change(input, { target: { value: '85' } })
    expect(screen.getAllByText('85').length).toBeGreaterThan(0)
  })

  it('updates purchase order limit via input', () => {
    render(<SettingsPage />)
    const input = screen.getByText('Purchase Order Limit').parentElement?.querySelector('input[type="number"]') as HTMLInputElement
    fireEvent.change(input, { target: { value: '2500' } })
    expect(input.value).toBe('2500')
  })

  it('keeps previous value when number input is cleared', () => {
    render(<SettingsPage />)
    const input = screen.getByText('Purchase Order Limit').parentElement?.querySelector('input[type="number"]') as HTMLInputElement
    fireEvent.change(input, { target: { value: '' } })
    expect(input.value).toBe('1000')
  })

  it('calls update mutation and shows saved confirmation', () => {
    const mutate = vi.fn((_payload: unknown, cb?: { onSuccess?: () => void }) => cb?.onSuccess?.())
    vi.mocked(useUpdateSettings).mockReturnValue({ mutate, isPending: false })
    render(<SettingsPage />)
    fireEvent.click(screen.getByText('Save Changes'))
    expect(mutate).toHaveBeenCalled()
    expect(screen.getByText('Saved Successfully')).toBeDefined()
  })

  it('survives unstable settings object identity without looping', () => {
    const unstable = vi.fn(() => ({
      data: { shadow_mode: true, fraud_threshold: 70, po_limit: 1000, pricing_limit: 5, reviews_rating_threshold: 4 },
      isLoading: false,
    }))
    vi.mocked(useSettings).mockImplementation(unstable)
    render(<SettingsPage />)
    expect(screen.getByText('System Settings')).toBeDefined()
    expect(unstable.mock.calls.length).toBeLessThanOrEqual(3)
  })
})