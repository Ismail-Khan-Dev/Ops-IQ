const API_PREFIX = "/api/v1"

const DEFAULT_TIMEOUT_MS = 30_000
const MAX_RETRIES = 3
const BASE_RETRY_DELAY_MS = 500

class ApiError extends Error {
  status: number
  body: unknown

  constructor(status: number, message: string, body?: unknown) {
    super(message)
    this.name = "ApiError"
    this.status = status
    this.body = body
  }
}

async function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  retryCount = 0,
): Promise<T> {
  // Same-origin request: the BFF route handlers and middleware in `src/app/api`
  // attach the authenticated backend identity. The browser never stores or
  // sends the raw API key.
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  }

  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS)

  try {
    const res = await fetch(path, { ...options, headers, signal: controller.signal })

    if (!res.ok) {
      const body = await res.json().catch(() => ({}))

      // Retry on 5xx errors
      if (res.status >= 500 && retryCount < MAX_RETRIES) {
        const delay = BASE_RETRY_DELAY_MS * Math.pow(2, retryCount)
        await sleep(delay)
        return request(path, options, retryCount + 1)
      }

      throw new ApiError(res.status, body.detail || res.statusText, body)
    }

    if (res.status === 204) return undefined as T
    return res.json()
  } catch (err) {
    if (err instanceof ApiError) throw err

    // Retry on network errors / timeout
    if (retryCount < MAX_RETRIES && (err instanceof TypeError || err instanceof DOMException)) {
      const delay = BASE_RETRY_DELAY_MS * Math.pow(2, retryCount)
      await sleep(delay)
      return request(path, options, retryCount + 1)
    }

    throw err
  } finally {
    clearTimeout(timeoutId)
  }
}

export const authApi = {
  login: (apiKey: string) =>
    request<{ status: string; operator?: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ api_key: apiKey }),
    }),
  logout: () => request<{ status: string }>("/api/auth/logout", { method: "POST" }),
  me: () =>
    request<{ status: string; operator?: string; authenticated?: boolean }>(
      "/api/auth/me"
    ),
}

export const healthApi = {
  check: () =>
    request<{
      status: string
      version?: string
      version_number?: string
      environment?: string
      uptime_seconds?: number
      dependencies?: Record<string, string>
      checks?: Record<string, string>
    }>(`${API_PREFIX}/health`),
}

export const agentApi = {
  list: () => request<{ agents: AgentStatus[]; total: number }>(`${API_PREFIX}/agents`),
  status: () => request<AgentStatus[]>(`${API_PREFIX}/agents/status`),
  setAutonomy: (agentId: string, level: "shadow" | "supervised" | "autonomous") =>
    request<AgentStatus>(`${API_PREFIX}/agents/${encodeURIComponent(agentId)}/autonomy`, {
      method: "PATCH",
      body: JSON.stringify({ level }),
    }),
  deploy: (agentType: string) =>
    request<{ status: string; agent_type: string }>(`${API_PREFIX}/agents/deploy`, {
      method: "POST",
      body: JSON.stringify({ agent_type: agentType }),
    }),
  logs: (params?: { agent?: string; limit?: number }) => {
    const qs = params ? `?${new URLSearchParams(params as Record<string, string>).toString()}` : ""
    return request<InferenceLog[]>(`${API_PREFIX}/agents/logs${qs}`)
  },
}

export const approvalApi = {
  list: (params?: { status?: string; agent?: string }) => {
    const qs = params ? `?${new URLSearchParams(params as Record<string, string>).toString()}` : ""
    return request<ApprovalAction[]>(`${API_PREFIX}/approvals${qs}`)
  },
  approve: (id: string) =>
    request<{ status: string }>(`${API_PREFIX}/approvals/${id}/approve`, { method: "POST" }),
  reject: (id: string) =>
    request<{ status: string }>(`${API_PREFIX}/approvals/${id}/reject`, { method: "POST" }),
  batch: (ids: string[], action: "approve" | "reject") =>
    request<{ processed: number }>(`${API_PREFIX}/approvals/batch`, {
      method: "POST",
      body: JSON.stringify({ action_ids: ids, action }),
    }),
}

export const analyticsApi = {
  summary: (days?: number) =>
    request<AnalyticsSummary>(`${API_PREFIX}/analytics` + (days ? `?days=${days}` : "")),
}

export const orderApi = {
  list: (params?: { page?: number; limit?: number; status?: string }) => {
    const sp = new URLSearchParams()
    if (params?.page) sp.set("page", String(params.page))
    if (params?.limit) sp.set("limit", String(params.limit))
    if (params?.status) sp.set("status", params.status)
    const qs = sp.toString()
    return request<{ orders: Order[]; total: number; page: number; limit: number }>(`${API_PREFIX}/orders${qs ? `?${qs}` : ""}`)
  },
}

export const productApi = {
  list: (params?: { page?: number; limit?: number }) => {
    const sp = new URLSearchParams()
    if (params?.page) sp.set("page", String(params.page))
    if (params?.limit) sp.set("limit", String(params.limit))
    const qs = sp.toString()
    return request<{ products: Product[]; total: number }>(`${API_PREFIX}/products${qs ? `?${qs}` : ""}`)
  },
}

export const cartRecoveryApi = {
  list: (params?: { status?: string }) => {
    const qs = params?.status ? `?status=${params.status}` : ""
    return request<CartItem[]>(`${API_PREFIX}/cart-recovery${qs}`)
  },
  analytics: () => request<CartRecoveryAnalytics>(`${API_PREFIX}/cart-recovery/analytics`),
}

export const reviewApi = {
  list: (params?: { sentiment?: string }) => {
    const qs = params?.sentiment ? `?sentiment=${params.sentiment}` : ""
    return request<Review[]>(`${API_PREFIX}/reviews${qs}`)
  },
}

export const supportApi = {
  listTickets: (params?: { status?: string; priority?: string; page?: number; limit?: number }) => {
    const sp = new URLSearchParams()
    if (params?.status) sp.set("status", params.status)
    if (params?.priority) sp.set("priority", params.priority)
    if (params?.page) sp.set("page", String(params.page))
    if (params?.limit) sp.set("limit", String(params.limit))
    const qs = sp.toString()
    return request<{ tickets: SupportTicket[]; total: number; page: number; limit: number }>(`${API_PREFIX}/support/tickets${qs ? `?${qs}` : ""}`)
  },
  getTicket: (id: string) => request<SupportTicket>(`${API_PREFIX}/support/tickets/${id}`),
  getAnalytics: (days = 7) => request<SupportAnalytics>(`${API_PREFIX}/support/analytics?days=${days}`),
}

export const securityApi = {
  events: (params?: { severity?: string }) => {
    const qs = params?.severity ? `?severity=${params.severity}` : ""
    return request<SecurityEvent[]>(`${API_PREFIX}/security/events${qs}`)
  },
  health: () => request<Record<string, string>>(`${API_PREFIX}/security/health`),
}

export const settingsApi = {
  get: () => request<StoreSettings>(`${API_PREFIX}/settings`),
  update: (data: Partial<StoreSettings>) =>
    request<StoreSettings>(`${API_PREFIX}/settings`, { method: "PATCH", body: JSON.stringify(data) }),
}

export const shopifyApi = {
  status: () => request<ShopifyStatus>(`${API_PREFIX}/shopify/status`),
  sync: () => request<{ status: string }>(`${API_PREFIX}/shopify/sync`, { method: "POST" }),
}

export interface AgentStatus {
  agent_id: string
  status: string
  streak: number
  autonomy_level: string
  total_decisions: number
  total_approvals: number
  total_rejections: number
  avg_confidence: number
}

export interface InferenceLog {
  id: string
  agent: string
  input: string
  output: string
  confidence: number
  latency_ms: number
  created_at: string
}

export interface ApprovalAction {
  id: string
  agent: string
  action_type: string
  status: string
  risk_level: string
  confidence_score: number
  created_at: string
  expires_at: string | null
  requires_hitl: boolean
  shadow_mode: boolean
  payload: Record<string, unknown>
  evidence: Record<string, unknown>
  impact: Record<string, unknown>
  reviewed_by: string | null
  reviewed_at: string | null
  rejection_reason: string | null
  operator_notes: string | null
}

export interface AnalyticsSummary {
  summary: {
    total_decisions: number
    approval_rate: number
    actions_auto_approved: number
    total_financial_impact: number
    avg_confidence: number
    avg_decision_time_minutes: number
  }
  graduation: Array<{
    agent_id: string
    streak: number
    autonomy_level: string
    total_decisions: number
    avg_confidence: number
  }>
  risk_distribution: Record<string, number>
  charts: {
    approval_rate_over_time: Array<Record<string, unknown>>
    volume_by_agent: Array<Record<string, unknown>>
    decision_time_dist: Record<string, number>
  }
}

export interface Order {
  id: string
  customer: string
  total: number
  status: string
  fraud_score: number
  created_at: string
}

export interface Product {
  id: string
  title: string
  price: number
  stock: number
  status: string
}

export interface CartItem {
  id: string
  customer_email: string
  items: Array<{ title: string; price: number; quantity: number }>
  total: number
  status: string
  created_at: string
}

export interface CartRecoveryAnalytics {
  total_abandoned: number
  total_recovered: number
  recovery_rate: number
  total_revenue_lost: number
  total_revenue_recovered: number
  average_cart_value: number
  average_recovery_time_hours: number
  top_recovery_strategy: string
  risk_distribution?: Record<string, number>
}

export interface Review {
  id: string
  author: string
  rating: number
  content: string
  sentiment: string
  created_at: string
}

export interface SupportTicket {
  id: string
  customer_email: string
  customer_name: string
  subject: string
  body: string
  category: string
  priority: string
  status: string
  channel: string
  order_id: string | null
  created_at: string
  messages: Array<{ id: string; sender_type: string; content: string; created_at: string }>
}

export interface SupportAnalytics {
  total_tickets: number
  open_tickets: number
  avg_response_time_hours: number
  avg_resolution_time_hours: number
  satisfaction_score: number
  first_contact_resolution_rate: number
  escalation_rate: number
  category_breakdown: Record<string, number>
  priority_breakdown: Record<string, number>
  sentiment_distribution: Record<string, number>
}

export interface SecurityEvent {
  id: string
  type: string
  severity: string
  description: string
  source_ip: string | null
  created_at: string
}

export interface StoreSettings {
  id: number
  shadow_mode: boolean
  fraud_threshold: number
  po_limit: number
  pricing_limit: number
  reviews_rating_threshold: number
}

export interface ShopifyStatus {
  configured: boolean
  shop_domain: string | null
  api_version: string
  webhook_topics: string[]
}

export { ApiError }