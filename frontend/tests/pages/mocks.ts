import { vi } from 'vitest'

const stableSettingsData: Record<string, unknown> = {
  shadow_mode: true,
  fraud_threshold: 70,
  po_limit: 1000,
  pricing_limit: 5,
  reviews_rating_threshold: 4,
}

vi.mock('@/lib/hooks', () => ({
  useHealth: vi.fn(() => ({ data: { status: 'ok', version: 'v2.5.0' }, isLoading: false })),
  useAgentStatus: vi.fn(() => ({
    data: [
      { agent_id: "FraudAgent", status: "active", streak: 12, autonomy_level: "supervised", total_decisions: 1200, total_approvals: 1100, avg_confidence: 0.94 },
      { agent_id: "InventoryAgent", status: "active", streak: 8, autonomy_level: "supervised", total_decisions: 800, total_approvals: 750, avg_confidence: 0.89 },
      { agent_id: "PricingAgent", status: "active", streak: 3, autonomy_level: "shadow", total_decisions: 400, total_approvals: 380, avg_confidence: 0.91 },
      { agent_id: "ReviewsAgent", status: "maintenance", streak: 1, autonomy_level: "shadow", total_decisions: 200, total_approvals: 190, avg_confidence: 0.87 },
      { agent_id: "MarketingAgent", status: "active", streak: 0, autonomy_level: "shadow", total_decisions: 100, total_approvals: 95, avg_confidence: 0.85 },
      { agent_id: "CartRecoveryAgent", status: "active", streak: 5, autonomy_level: "supervised", total_decisions: 300, total_approvals: 280, avg_confidence: 0.88 },
      { agent_id: "SupportAgent", status: "active", streak: 2, autonomy_level: "shadow", total_decisions: 150, total_approvals: 140, avg_confidence: 0.86 },
    ],
    isLoading: false,
  })),
  useApprovals: vi.fn(() => ({ data: [], isLoading: false })),
  useAnalytics: vi.fn(() => ({
    data: {
      summary: {
        total_financial_impact: 124892.4,
        total_decisions: 14208,
        approval_rate: 82.1,
        actions_auto_approved: 11500,
        avg_confidence: 0.92,
        avg_decision_time_minutes: 1.4,
      },
      graduation: [
        { agent_id: "FraudAgent", streak: 5, autonomy_level: "supervised", total_decisions: 1200, avg_confidence: 0.94 },
        { agent_id: "InventoryAgent", streak: 3, autonomy_level: "supervised", total_decisions: 800, avg_confidence: 0.89 },
        { agent_id: "PricingAgent", streak: 2, autonomy_level: "shadow", total_decisions: 400, avg_confidence: 0.91 },
        { agent_id: "ReviewsAgent", streak: 1, autonomy_level: "shadow", total_decisions: 200, avg_confidence: 0.87 },
        { agent_id: "MarketingAgent", streak: 0, autonomy_level: "shadow", total_decisions: 100, avg_confidence: 0.85 },
      ],
      risk_distribution: { critical: 2, high: 5, medium: 10, low: 30 },
      charts: {
        approval_rate_over_time: [{ date: "Jan 15", FraudAgent: 10, InventoryAgent: 5, PricingAgent: 3, ReviewsAgent: 2, MarketingAgent: 1 }],
        volume_by_agent: [{ day: "Mon", Fraud: 10, Inventory: 5, Pricing: 3, Reviews: 2, Marketing: 1 }],
        decision_time_dist: { under_1m: 50, "1m_5m": 30, "5m_30m": 15, over_30m: 5 },
      },
    },
    isLoading: false,
  })),
  useSettings: vi.fn(() => ({ data: stableSettingsData, isLoading: false })),
  useUpdateSettings: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useSupportTickets: vi.fn(() => ({ data: [], isLoading: false })),
  useCartRecoveryStats: vi.fn(() => ({ data: {}, isLoading: false })),
  useCartRecoveryAnalytics: vi.fn(() => ({ data: {}, isLoading: false })),
  useShopifyStatus: vi.fn(() => ({ data: {}, isLoading: false })),
  useShopifySync: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useOrders: vi.fn(() => ({ data: [], isLoading: false })),
  useProducts: vi.fn(() => ({ data: [], isLoading: false })),
  useReviews: vi.fn(() => ({ data: [], isLoading: false })),
  useSecurityEvents: vi.fn(() => ({ data: [], isLoading: false })),
  useSetAgentAutonomy: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}))

vi.mock('@/app/providers', () => ({
  useWs: vi.fn(() => ({ isConnected: true })),
}))

vi.mock('next/navigation', () => ({
  useRouter: vi.fn(() => ({ push: vi.fn() })),
  usePathname: vi.fn(() => '/'),
}))

vi.mock('@/lib/auth-store', () => ({
  useAuthStore: vi.fn(() => ({
    login: vi.fn().mockResolvedValue(true),
    logout: vi.fn(),
    isLoading: false,
    error: null,
    clearError: vi.fn(),
    apiKey: null,
  })),
}))
