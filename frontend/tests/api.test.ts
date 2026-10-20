import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  authApi,
  healthApi,
  agentApi,
  approvalApi,
  analyticsApi,
  orderApi,
  settingsApi,
  ApiError,
} from '@/lib/api'

const mockFetch = vi.fn()
global.fetch = mockFetch

function jsonResponse(status: number, body: unknown, statusText = 'OK') {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText,
    json: async () => body,
  } as any
}

beforeEach(() => {
  mockFetch.mockReset()
  vi.useRealTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('authApi.login', () => {
  it('returns success on valid login', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(200, { status: 'ok', operator: 'test-operator' }))

    const result = await authApi.login('test-key')
    expect(result.status).toBe('ok')
    expect(result.operator).toBe('test-operator')
  })

  it('throws ApiError on 401', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(401, { detail: 'Invalid API key' }))

    await expect(authApi.login('bad-key')).rejects.toThrow(ApiError)
  })

  it('sends correct request body', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(200, { status: 'ok' }))

    await authApi.login('my-key')

    const [url, options] = mockFetch.mock.calls[0]
    expect(url).toContain('/api/auth/login')
    expect(options.method).toBe('POST')
    expect(JSON.parse(options.body)).toEqual({ api_key: 'my-key' })
  })
})

describe('ApiError', () => {
  it('stores status and message', () => {
    const err = new ApiError(404, 'Not Found')
    expect(err.status).toBe(404)
    expect(err.message).toBe('Not Found')
    expect(err.name).toBe('ApiError')
  })

  it('stores body', () => {
    const err = new ApiError(500, 'Error', { detail: 'something' })
    expect(err.body).toEqual({ detail: 'something' })
  })
})

describe('request path construction', () => {
  it('prefixes API paths and sends JSON headers', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(200, []))
    await healthApi.check()

    const [url, options] = mockFetch.mock.calls[0]
    expect(url).toBe('/api/v1/health')
    expect(options.headers['Content-Type']).toBe('application/json')
  })

  it('builds query strings from params', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(200, []))
    await agentApi.logs({ agent: 'Fraud Agent', limit: 5 })

    const [url, options] = mockFetch.mock.calls[0]
    expect(url).toBe('/api/v1/agents/logs?agent=Fraud+Agent&limit=5')
    expect(options.method).toBeUndefined()
  })

  it('omits query string when no params given', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(200, []))
    await approvalApi.list()

    const [url] = mockFetch.mock.calls[0]
    expect(url).toBe('/api/v1/approvals')
  })

  it('sends PATCH body for settings update', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(200, {}))
    await settingsApi.update({ shadow_mode: true })

    const [url, options] = mockFetch.mock.calls[0]
    expect(url).toBe('/api/v1/settings')
    expect(options.method).toBe('PATCH')
    expect(JSON.parse(options.body)).toEqual({ shadow_mode: true })
  })

  it('sends batched approval bodies', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(200, { processed: 2 }))
    await approvalApi.batch(['a', 'b'], 'approve')

    const [url, options] = mockFetch.mock.calls[0]
    expect(url).toBe('/api/v1/approvals/batch')
    expect(options.method).toBe('POST')
    expect(JSON.parse(options.body)).toEqual({ action_ids: ['a', 'b'], action: 'approve' })
  })

  it('appends days param and sends POST for deploy/analytics paths', async () => {
    mockFetch
      .mockResolvedValueOnce(jsonResponse(200, {}))
      .mockResolvedValueOnce(jsonResponse(200, {}))
    await analyticsApi.summary(30)
    expect(mockFetch.mock.calls[0][0]).toBe('/api/v1/analytics?days=30')

    await agentApi.deploy('FraudAgent')
    const [url, options] = mockFetch.mock.calls[1]
    expect(url).toBe('/api/v1/agents/deploy')
    expect(options.method).toBe('POST')
    expect(JSON.parse(options.body)).toEqual({ agent_type: 'FraudAgent' })
  })

  it('builds partial order list query params', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(200, {}))
    await orderApi.list({ page: 2, status: 'pending' })
    expect(mockFetch.mock.calls[0][0]).toBe('/api/v1/orders?page=2&status=pending')
  })
})

describe('request response handling', () => {
  it('returns undefined on 204', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, status: 204, json: async () => ({}) } as any)
    await expect(authApi.logout()).resolves.toBeUndefined()
  })

  it('falls back to statusText when error body is not JSON', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 400,
      statusText: 'Bad Request',
      json: async () => {
        throw new SyntaxError('bad json')
      },
    } as any)

    await expect(authApi.login('k')).rejects.toMatchObject({
      name: 'ApiError',
      status: 400,
      message: 'Bad Request',
    })
  })
})

describe('request retries', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  it('retries once on 5xx then succeeds', async () => {
    mockFetch
      .mockResolvedValueOnce(jsonResponse(503, {}, 'Service Unavailable'))
      .mockResolvedValueOnce(jsonResponse(200, { ok: true }))

    const promise = healthApi.check()
    await vi.advanceTimersByTimeAsync(600)
    await expect(promise).resolves.toEqual({ ok: true })
    expect(mockFetch).toHaveBeenCalledTimes(2)
  })

  it('exhausts retries and throws ApiError on persistent 5xx', async () => {
    mockFetch.mockResolvedValue(jsonResponse(503, {}, 'Service Unavailable'))

    const promise = healthApi.check()
    const assertion = expect(promise).rejects.toMatchObject({
      name: 'ApiError',
      status: 503,
      message: 'Service Unavailable',
    })
    await vi.advanceTimersByTimeAsync(4000)
    await assertion
    expect(mockFetch).toHaveBeenCalledTimes(4)
  })

  it('retries on network TypeError then succeeds', async () => {
    mockFetch
      .mockRejectedValueOnce(new TypeError('fetch failed'))
      .mockResolvedValueOnce(jsonResponse(200, { ok: true }))

    const promise = healthApi.check()
    await vi.advanceTimersByTimeAsync(600)
    await expect(promise).resolves.toEqual({ ok: true })
    expect(mockFetch).toHaveBeenCalledTimes(2)
  })

  it('retries on abort (timeout) errors then succeeds', async () => {
    mockFetch
      .mockRejectedValueOnce(new DOMException('The operation was aborted.', 'AbortError'))
      .mockResolvedValueOnce(jsonResponse(200, { ok: true }))

    const promise = healthApi.check()
    await vi.advanceTimersByTimeAsync(600)
    await expect(promise).resolves.toEqual({ ok: true })
    expect(mockFetch).toHaveBeenCalledTimes(2)
  })

  it('rethrows non-retryable rejection without retrying', async () => {
    mockFetch.mockRejectedValueOnce(new Error('boom'))

    await expect(healthApi.check()).rejects.toThrow('boom')
    expect(mockFetch).toHaveBeenCalledTimes(1)
  })
})