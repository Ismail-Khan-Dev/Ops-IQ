"use client"

import { useState } from "react"
import {
  DollarSign,
  Bot,
  AlertTriangle,
  Wifi,
  Server,
  Activity,
  Shield,
  Box,
  Tag,
  Headphones,
  Truck,
  Star,
  TrendingUp,
  ChevronLeft,
  ChevronRight,
  Clock,
  Zap,
  Database,
  Layers,
} from "lucide-react"
import Shell from "@/components/layout/Shell"
import { useAgentStatus, useApprovals, useAnalytics, useHealth } from "@/lib/hooks"
import { useWs } from "@/app/providers"
import type { AgentStatus, ApprovalAction } from "@/lib/api"

function getRiskBarClass(score: number): string {
  if (score >= 75) return "risk-high"
  if (score >= 50) return "risk-medium"
  return "risk-low"
}

function getRiskScore(risk: string): number {
  switch (risk) {
    case "critical": return 92
    case "high": return 82
    case "medium": return 67
    case "low": return 32
    default: return 50
  }
}

function getConfidenceClass(confidence: number): string {
  if (confidence >= 0.8) return "confidence-high"
  if (confidence >= 0.5) return "confidence-medium"
  return "confidence-low"
}

const agentIcons: Record<string, typeof Shield> = {
  FraudAgent: Shield,
  InventoryAgent: Box,
  PricingAgent: Tag,
  ReviewsAgent: Star,
  MarketingAgent: TrendingUp,
  fraud_detection: Shield,
  inventory_management: Box,
  price_optimization: Tag,
  customer_support: Headphones,
  logistics: Truck,
  review_moderation: Star,
  seo_optimization: TrendingUp,
}

const agentColors: Record<string, string> = {
  FraudAgent: "bg-danger-light text-danger",
  InventoryAgent: "bg-info-light text-info",
  PricingAgent: "bg-warning-light text-warning",
  ReviewsAgent: "bg-primary-light text-primary",
  MarketingAgent: "bg-success-light text-success",
  fraud_detection: "bg-danger-light text-danger",
  inventory_management: "bg-info-light text-info",
  price_optimization: "bg-warning-light text-warning",
  customer_support: "bg-primary-light text-primary",
  logistics: "bg-success-light text-success",
  review_moderation: "bg-info-light text-info",
  seo_optimization: "bg-primary-light text-primary",
}

const agentDisplayName: Record<string, string> = {
  FraudAgent: "Fraud",
  InventoryAgent: "Inventory",
  PricingAgent: "Pricing",
  ReviewsAgent: "Reviews",
  MarketingAgent: "Marketing",
}

export default function DashboardPage() {
  const { data: healthData, isLoading: healthLoading } = useHealth()
  const { data: agentsData, isLoading: agentsLoading } = useAgentStatus()
  const { data: approvalsData, isLoading: approvalsLoading } = useApprovals({ status: "pending" })
  const { data: analyticsData, isLoading: analyticsLoading } = useAnalytics()
  const { isConnected } = useWs()
  const [page, setPage] = useState(0)

  const agents: AgentStatus[] = agentsData ?? []
  const pendingDecisions: ApprovalAction[] = approvalsData ?? []

  // Real KPI values only; no fabricated fallbacks.
  const revenue = analyticsData?.summary?.total_financial_impact ?? null
  const totalDecisions = analyticsData?.summary?.total_decisions ?? null
  const approvalRate = analyticsData?.summary?.approval_rate ?? null
  const avgConfidence = analyticsData?.summary?.avg_confidence ?? null
  const pendingCount = pendingDecisions.length
  const flaggedCount = pendingDecisions.filter(
    (d) => d.risk_level === "high" || d.risk_level === "critical"
  ).length

  const hasApprovalData = approvalsData !== undefined
  const hasAnalyticsData = analyticsData !== undefined
  const deps = healthData?.dependencies ?? null

  const pageSize = 4
  const totalPages = Math.max(1, Math.ceil(pendingDecisions.length / pageSize))
  const visibleDecisions = pendingDecisions.slice(page * pageSize, (page + 1) * pageSize)

  return (
    <Shell title="Command Center" subtitle="Real-time operations overview">
      <div className="flex flex-col">
        {/* Metric Cards */}
        <div className="grid grid-cols-4 gap-4 mb-6">
          <div className="metric-card">
            <div className="flex items-center justify-between mb-3">
              <span className="metric-label">Financial Impact</span>
              <div className="w-9 h-9 rounded-lg bg-success-light flex items-center justify-center">
                <DollarSign className="w-4 h-4 text-success" />
              </div>
            </div>
            <div className="metric-value">
              {revenue === null
                ? healthLoading || analyticsLoading ? "…" : "—"
                : `$${revenue.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
            </div>
            <div className="metric-change text-text-muted flex items-center gap-1 mt-1">
              <Activity className="w-3 h-3" />
              {hasAnalyticsData ? "Approved impact" : "No data yet"}
            </div>
          </div>

          <div className="metric-card">
            <div className="flex items-center justify-between mb-3">
              <span className="metric-label">Decisions Made</span>
              <div className="w-9 h-9 rounded-lg bg-primary-light flex items-center justify-center">
                <Bot className="w-4 h-4 text-primary" />
              </div>
            </div>
            <div className="metric-value">
              {totalDecisions === null
                ? healthLoading || analyticsLoading ? "…" : "—"
                : totalDecisions.toLocaleString()}
            </div>
            <div className="metric-change text-text-muted flex items-center gap-1 mt-1">
              <Clock className="w-3 h-3" />
              {approvalRate === null
                ? "Approval rate pending"
                : `Approval rate ${approvalRate}%`}
            </div>
          </div>

          <div className="metric-card">
            <div className="flex items-center justify-between mb-3">
              <span className="metric-label">Pending Reviews</span>
              <div className="w-9 h-9 rounded-lg bg-warning-light flex items-center justify-center">
                <Clock className="w-4 h-4 text-warning" />
              </div>
            </div>
            <div className="metric-value">
              {approvalsLoading ? "…" : pendingCount}
            </div>
            <div className="metric-change text-text-muted flex items-center gap-1 mt-1">
              <Activity className="w-3 h-3" />
              {hasApprovalData ? "Awaiting review" : "No data yet"}
            </div>
          </div>

          <div className="metric-card">
            <div className="flex items-center justify-between mb-3">
              <span className="metric-label">Flagged Orders</span>
              <div className="w-9 h-9 rounded-lg bg-danger-light flex items-center justify-center">
                <AlertTriangle className="w-4 h-4 text-danger" />
              </div>
            </div>
            <div className="metric-value">
              {approvalsLoading ? "…" : flaggedCount}
            </div>
            <div className="metric-change text-text-muted flex items-center gap-1 mt-1">
              <Activity className="w-3 h-3" />
              {hasApprovalData ? "High/critical pending" : "No data yet"}
            </div>
          </div>
        </div>

        {/* Two-column layout */}
        <div className="grid grid-cols-12 gap-6 mb-6">
          {/* Left: Pending Approvals */}
          <div className="col-span-8 card">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-primary-light flex items-center justify-center">
                  <Activity className="w-4 h-4 text-primary" />
                </div>
                <h2 className="font-display font-semibold text-text-primary">Pending Approvals</h2>
              </div>
            </div>

            {approvalsLoading ? (
              <div className="py-10 text-center text-sm text-text-muted">Loading…</div>
            ) : pendingDecisions.length === 0 ? (
              <div className="py-10 text-center text-sm text-text-muted">
                {hasApprovalData
                  ? "No decisions awaiting review."
                  : "Approvals endpoint is unreachable — no data to show."}
              </div>
            ) : (
              <>
                <div className="table-container">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>ORDER ID</th>
                        <th>RISK SCORE</th>
                        <th>AI CONFIDENCE</th>
                        <th className="text-right">IMPACT</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visibleDecisions.map((d) => {
                        const riskScore = getRiskScore(d.risk_level)
                        const confidence = d.confidence_score ?? 0
                        const financialImpact =
                          (d.impact?.financial_impact as number) ??
                          (d.payload?.financial_impact as number) ??
                          0
                        return (
                          <tr key={d.id}>
                            <td className="font-mono text-sm text-primary font-medium">{d.id}</td>
                            <td>
                              <div className="flex items-center gap-3">
                                <div className="risk-bar flex-1 max-w-[120px]">
                                  <div
                                    className={getRiskBarClass(riskScore)}
                                    style={{ width: `${riskScore}%` }}
                                  />
                                </div>
                                <span className="font-mono text-sm text-text-primary font-medium">{riskScore}%</span>
                              </div>
                            </td>
                            <td>
                              <span className={getConfidenceClass(confidence)}>
                                {(confidence * 100).toFixed(1)}%
                              </span>
                            </td>
                            <td className="text-right font-mono text-sm text-text-primary font-medium">
                              ${financialImpact.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>

                <div className="flex items-center justify-between pt-3 mt-3 border-t border-border">
                  <span className="text-sm text-text-muted">
                    Showing {visibleDecisions.length} of {pendingDecisions.length} pending orders
                  </span>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setPage(Math.max(0, page - 1))}
                      disabled={page === 0}
                      className="p-1.5 rounded-md hover:bg-surface-3 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                      aria-label="Previous page"
                    >
                      <ChevronLeft className="w-4 h-4 text-text-secondary" />
                    </button>
                    <button
                      onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
                      disabled={page >= totalPages - 1}
                      className="p-1.5 rounded-md hover:bg-surface-3 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                      aria-label="Next page"
                    >
                      <ChevronRight className="w-4 h-4 text-text-secondary" />
                    </button>
                  </div>
                </div>
              </>
            )}
          </div>

          {/* Right: Sidebar cards */}
          <div className="col-span-4 space-y-4">
            {/* System Health */}
            <div className="card">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <Activity className="w-4 h-4 text-success" />
                  <h3 className="text-sm font-semibold text-text-primary">System Health</h3>
                </div>
                <span className="label-caps">
                  {healthData?.status === "ok" ? "OPERATIONAL" : "CHECK"}
                </span>
              </div>

              <div className="space-y-3">
                <div className="flex items-center justify-between p-3 rounded-lg bg-surface-3">
                  <span className="text-sm text-text-secondary">WebSocket Status</span>
                  <div className="flex items-center gap-2">
                    <div className={`w-2 h-2 rounded-full ${isConnected ? "bg-success animate-pulse" : "bg-danger"}`} />
                    <span className={`text-xs font-medium ${isConnected ? "text-success" : "text-danger"}`}>
                      {isConnected ? "CONNECTED" : "DISCONNECTED"}
                    </span>
                  </div>
                </div>

                {deps ? (
                  Object.entries(deps).map(([key, value]) => (
                    <div key={key} className="flex items-center justify-between p-3 rounded-lg bg-surface-3">
                      <span className="text-sm text-text-secondary capitalize">{key.replace(/_/g, " ")}</span>
                      <span className={`text-xs font-medium ${String(value).toLowerCase() === "healthy" || String(value).toLowerCase() === "loaded" ? "text-success" : "text-warning"}`}>
                        {String(value).toUpperCase()}
                      </span>
                    </div>
                  ))
                ) : (
                  <div className="p-3 rounded-lg bg-surface-3 text-sm text-text-muted">
                    {healthLoading ? "Checking backend health…" : "Health endpoint unreachable."}
                  </div>
                )}
              </div>
            </div>

            {/* Backend Info */}
            <div className="card">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-semibold text-text-primary">Backend</h3>
              </div>

              <div className="space-y-3">
                <div className="flex items-center gap-3 p-3 rounded-lg bg-surface-3">
                  <div className="p-2 rounded-lg bg-primary-light">
                    <Server className="w-4 h-4 text-primary" />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-text-primary">API</span>
                      <span className={`font-mono text-xs ${healthData?.status === "ok" ? "text-success" : "text-danger"}`}>
                        {healthData?.status?.toUpperCase() ?? "UNKNOWN"}
                      </span>
                    </div>
                    <div className="flex items-center justify-between mt-0.5">
                      <span className="text-xs text-text-muted">
                        {healthData?.environment ?? "—"}
                      </span>
                      <span className="text-xs text-text-muted">
                        v{healthData?.version_number ?? "—"}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-3 p-3 rounded-lg bg-surface-3">
                  <div className="p-2 rounded-lg bg-info-light">
                    <Wifi className="w-4 h-4 text-info" />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-text-primary">WebSocket</span>
                      <span className={`font-mono text-xs ${isConnected ? "text-success" : "text-danger"}`}>
                        {isConnected ? "LIVE" : "OFFLINE"}
                      </span>
                    </div>
                    <div className="flex items-center justify-between mt-0.5">
                      <span className="text-xs text-text-muted">Real-time event stream</span>
                      <span className="text-xs text-text-muted">{avgConfidence === null ? "—" : `conf ${(avgConfidence * 100).toFixed(1)}%`}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Fleet summary */}
            <div className="card">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <Layers className="w-4 h-4 text-primary" />
                  <h3 className="text-sm font-semibold text-text-primary">Agent Queue</h3>
                </div>
              </div>
              <div className="p-3 rounded-lg bg-surface-3 text-sm text-text-muted">
                {deps?.task_queue ? `Task queue depth: ${deps.task_queue}` : "Task queue status unavailable."}
              </div>
            </div>
          </div>
        </div>

        {/* Agent Fleet Status */}
        <div className="card mb-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-primary-light flex items-center justify-center">
                <Bot className="w-4 h-4 text-primary" />
              </div>
              <h2 className="font-display font-semibold text-text-primary">Agent Fleet Status</h2>
            </div>
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <div className="dot-green" />
                <span className="text-sm text-text-secondary">{agents.filter((a) => a.status === "active").length} Active</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="dot-gray" />
                <span className="text-sm text-text-secondary">{agents.length} Total</span>
              </div>
            </div>
          </div>

          {agentsLoading ? (
            <div className="py-8 text-center text-sm text-text-muted">Loading agent status…</div>
          ) : agents.length === 0 ? (
            <div className="py-8 text-center text-sm text-text-muted">
              No agent status available from the backend.
            </div>
          ) : (
            <div className="grid grid-cols-5 divide-x divide-border">
              {agents.map((agent) => {
                const key = agent.agent_id
                const Icon = agentIcons[key] || Zap
                return (
                  <div key={key} className="p-4 hover:bg-surface-2 transition-colors">
                    <div className="flex items-center justify-between mb-3">
                      <div className={`p-2 rounded-lg ${agentColors[key] || "bg-primary-light text-primary"}`}>
                        <Icon className="w-4 h-4" />
                      </div>
                      <div className={`dot-${agent.status === "active" ? "green" : "gray"}`} />
                    </div>
                    <h3 className="text-sm font-medium text-text-primary mb-3">
                      {agentDisplayName[key] || key}
                    </h3>
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-text-muted">Decisions</span>
                        <span className="font-mono text-xs text-text-secondary">{agent.total_decisions}</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-text-muted">Confidence</span>
                        <span className="font-mono text-xs text-primary">{(agent.avg_confidence * 100).toFixed(1)}%</span>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-center gap-2 py-4 text-[11px] font-mono text-text-muted">
          <span>© 2024 OpsIQ {healthData?.version_number ? `v${healthData.version_number}` : ""}</span>
          <span className="mx-1">|</span>
          <span className="flex items-center gap-1.5">
            <span className={`dot-${healthData?.status === "ok" ? "green" : "amber"}`} />
            {healthData?.status === "ok"
              ? "All Systems Operational"
              : healthData?.status === "degraded"
                ? "System Degraded"
                : "Backend Status Unknown"}
          </span>
        </div>
      </div>
    </Shell>
  )
}