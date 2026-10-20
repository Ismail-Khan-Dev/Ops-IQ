// ── Agent Types ──────────────────────────────────────────

export type AgentStatus = 'active' | 'paused' | 'error' | 'processing'

export interface Agent {
  id: string
  name: string
  displayName: string
  description: string
  status: AgentStatus
  accuracy: number
  confidence: number
  processedToday: number
  lastActivity: string
  uptime: number
  errorRate: number
  avgResponseTime: number
  color: string
}

// ── Decision Types ───────────────────────────────────────

export type DecisionStatus = 'pending' | 'approved' | 'flagged' | 'rejected'
export type DecisionAction = 'approve' | 'flag' | 'reject' | 'hold'

export interface Decision {
  id: string
  orderId: string
  agent: string
  type: string
  status: DecisionStatus
  confidence: number
  riskScore?: number
  reasoning: string
  recommendedAction: string
  data: Record<string, any>
  createdAt: string
  updatedAt: string
}

// ── Order Types ──────────────────────────────────────────

export type OrderStatus = 'pending' | 'processing' | 'shipped' | 'delivered' | 'cancelled'

export interface Order {
  id: string
  shopifyId: string
  customerEmail: string
  customerName: string
  total: number
  currency: string
  status: OrderStatus
  riskScore: number
  itemCount: number
  shippingAddress: Address
  createdAt: string
  updatedAt: string
}

export interface Address {
  city: string
  state: string
  country: string
  zip: string
}

// ── Cart Recovery Types ──────────────────────────────────

export type RecoveryStatus = 'pending' | 'sent' | 'recovered' | 'expired'
export type RecoveryStrategy = 'discount_10' | 'discount_15' | 'free_shipping' | 'urgency' | 'social_proof'

export interface AbandonedCart {
  id: string
  customerEmail: string
  items: CartItem[]
  total: number
  abandonedAt: string
  strategy: RecoveryStrategy
  status: RecoveryStatus
  discountCode?: string
  recoveredAt?: string
}

export interface CartItem {
  name: string
  price: number
  quantity: number
}

// ── Support Types ────────────────────────────────────────

export type TicketStatus = 'open' | 'in_progress' | 'resolved' | 'closed'
export type TicketPriority = 'low' | 'medium' | 'high' | 'urgent'
export type TicketSentiment = 'positive' | 'neutral' | 'negative'

export interface SupportTicket {
  id: string
  customerEmail: string
  customerName: string
  subject: string
  message: string
  status: TicketStatus
  priority: TicketPriority
  sentiment: TicketSentiment
  category: string
  aiResponse?: string
  assignedTo?: string
  createdAt: string
  updatedAt: string
}

// ── Activity Types ───────────────────────────────────────

export type ActivityType = 'decision' | 'alert' | 'system' | 'agent'

export interface Activity {
  id: string
  type: ActivityType
  agent: string
  action: string
  description: string
  confidence?: number
  metadata?: Record<string, any>
  timestamp: string
}

// ── Metric Types ─────────────────────────────────────────

export interface MetricCard {
  label: string
  value: string | number
  delta?: number
  deltaLabel?: string
  icon: string
  color: string
}

// ── WebSocket Types ──────────────────────────────────────

export type WSEvent =
  | { type: 'decision_update'; data: Decision }
  | { type: 'agent_status'; agent: string; status: AgentStatus }
  | { type: 'alert'; severity: 'critical' | 'warning' | 'info'; message: string }
  | { type: 'activity'; agent: string; action: string; confidence: number }

// ── API Types ────────────────────────────────────────────

export interface ApiResponse<T> {
  data: T
  success: boolean
  message?: string
}

export interface PaginatedResponse<T> {
  data: T[]
  total: number
  page: number
  pageSize: number
  hasMore: boolean
}

// ── Filter Types ─────────────────────────────────────────

export interface DecisionFilters {
  status?: DecisionStatus
  agent?: string
  dateFrom?: string
  dateTo?: string
}

export interface OrderFilters {
  status?: OrderStatus
  dateFrom?: string
  dateTo?: string
  minTotal?: number
  maxTotal?: number
}
