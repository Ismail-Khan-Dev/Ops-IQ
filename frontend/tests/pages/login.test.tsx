import { describe, it, expect, vi } from 'vitest'
import type { Mock } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import './mocks'
import { useAuthStore } from '@/lib/auth-store'
import { useRouter } from 'next/navigation'
import LoginPage from '@/app/login/page'

vi.mock('next/navigation', () => ({
  useRouter: vi.fn(() => ({ push: vi.fn() })),
  usePathname: vi.fn(() => '/'),
}))

interface AuthOverrides {
  login?: Mock
  logout?: Mock
  isLoading?: boolean
  error?: string | null
  clearError?: Mock
  apiKey?: string | null
}

function mockAuth(overrides: AuthOverrides = {}) {
  const login = overrides.login ?? vi.fn().mockResolvedValue(true)
  const mocked = {
    login,
    logout: vi.fn(),
    isLoading: false,
    error: null,
    clearError: vi.fn(),
    apiKey: null,
    ...overrides,
  }
  vi.mocked(useAuthStore).mockReturnValue(mocked as never)
  return { login, mocked }
}

function mockRouter() {
  const push = vi.fn()
  vi.mocked(useRouter).mockReturnValue({ push } as never)
  return push
}

describe('LoginPage', () => {
  it('renders login form with API key input', () => {
    render(<LoginPage />)
    expect(screen.getByPlaceholderText('opsiq-dev-key-2024')).toBeDefined()
    expect(screen.getByText('Access Command Center')).toBeDefined()
  })

  it('renders OpsIQ branding', () => {
    render(<LoginPage />)
    expect(screen.getByText('OpsIQ')).toBeDefined()
    expect(screen.getByText('AI Automation Interface')).toBeDefined()
  })

  it('renders documentation and security links', () => {
    render(<LoginPage />)
    expect(screen.getByText('Documentation')).toBeDefined()
    expect(screen.getByText('Security Audit')).toBeDefined()
    expect(screen.getByText('Status')).toBeDefined()
  })

  it('disables submit when API key is empty', () => {
    render(<LoginPage />)
    const button = screen.getByRole('button', { name: /Access Command Center/i })
    expect(button.hasAttribute('disabled')).toBe(true)
  })

  it('enables submit when API key is entered', () => {
    render(<LoginPage />)
    const input = screen.getByPlaceholderText('opsiq-dev-key-2024')
    fireEvent.change(input, { target: { value: 'test-key' } })
    const button = screen.getByRole('button', { name: /Access Command Center/i })
    expect(button.hasAttribute('disabled')).toBe(false)
  })

  it('shows system operational status', () => {
    render(<LoginPage />)
    expect(screen.getByText('System Operational')).toBeDefined()
  })

  it('submits API key and redirects on success', async () => {
    const { login } = mockAuth()
    const push = mockRouter()
    render(<LoginPage />)

    fireEvent.change(screen.getByPlaceholderText('opsiq-dev-key-2024'), { target: { value: 'my-key' } })
    fireEvent.submit(screen.getByPlaceholderText('opsiq-dev-key-2024').closest('form') as HTMLFormElement)

    await waitFor(() => expect(login).toHaveBeenCalledWith('my-key'))
    expect(push).toHaveBeenCalledWith('/')
  })

  it('does not authenticate when API key is empty', async () => {
    const { login } = mockAuth()
    const push = mockRouter()
    render(<LoginPage />)

    fireEvent.submit(screen.getByPlaceholderText('opsiq-dev-key-2024').closest('form') as HTMLFormElement)

    expect(login).not.toHaveBeenCalled()
    expect(push).not.toHaveBeenCalled()
  })

  it('does not redirect when login fails', async () => {
    mockAuth({ login: vi.fn().mockResolvedValue(false) })
    const push = mockRouter()
    render(<LoginPage />)

    fireEvent.change(screen.getByPlaceholderText('opsiq-dev-key-2024'), { target: { value: 'bad-key' } })
    fireEvent.submit(screen.getByPlaceholderText('opsiq-dev-key-2024').closest('form') as HTMLFormElement)

    await waitFor(() => expect(push).not.toHaveBeenCalled())
  })

  it('renders the error banner from the store', () => {
    mockAuth({ error: 'Invalid API key' })
    render(<LoginPage />)
    expect(screen.getByText('Invalid API key')).toBeDefined()
  })

  it('clears the error when the user types', () => {
    const { mocked } = mockAuth({ error: 'Invalid API key' })
    render(<LoginPage />)

    fireEvent.change(screen.getByPlaceholderText('opsiq-dev-key-2024'), { target: { value: 'k' } })
    expect(mocked.clearError).toHaveBeenCalled()
  })

  it('shows loading state while authenticating', () => {
    mockAuth({ isLoading: true })
    render(<LoginPage />)
    expect(screen.getByText('Connecting...')).toBeDefined()
  })
})
