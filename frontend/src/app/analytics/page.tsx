"use client"

import { useState, type ReactNode } from "react"
import {
  TrendingUp,
  DollarSign,
  Clock,
  Target,
  Download,
} from "lucide-react"
import Shell from "@/components/layout/Shell"
import { useAnalytics } from "@/lib/hooks"

const timeRanges = ["30D", "7D", "24H"] as const

const riskLevels = [
  { key: "critical", label: "Critical", severityClass: "badge-danger", barColor: "bg-danger" },
  { key: "high", label: "High", severityClass: "badge-warning", barColor: "bg-warning" },
  { key: "medium", label: "Medium", severityClass: "badge-info", barColor: "bg-info" },
  { key: "low", label: "Low", severityClass: "badge-success", barColor: "bg-success" },
] as const

const formatCurrency = (value: number) =>
  value.toLocaleString("en-US", { style: "currency", currency: "USD" })

const formatNumber = (value: number) => value.toLocaleString("en-US")

export default function AnalyticsPage() {
  const [timeRange, setTimeRange] = useState<string>("30D")
  const { data, isLoading, isError } = useAnalytics()

  const actions = (
    <div className="flex items-center gap-2">
      <div className="flex items-center gap-1 bg-surface rounded-card p-1 border border-border">
        {timeRanges.map((range) => (
          <button
            key={range}
            onClick={() => setTimeRange(range)}
            className={
              timeRange === range
                ? "px-3 py-1.5 rounded-button text-xs font-medium bg-primary/15 text-primary transition-colors"
                : "px-3 py-1.5 rounded-button text-xs font-medium text-text-muted hover:text-text-secondary transition-colors"
            }
          >
            {range}
          </button>
        ))}
      </div>
      <button className="btn-ghost">
        <Download className="w-4 h-4" />
        Export
      </button>
    </div>
  )

  let body: ReactNode

  if (isLoading) {
    body = (
      <div className="card">
        <p className="text-body-sm text-text-muted">Loading…</p>
      </div>
    )
  } else if (isError) {
    body = (
      <div className="card">
        <p className="text-body-sm text-text-muted">Analytics endpoint unreachable — no data to display.</p>
      </div>
    )
  } else if (!data || !data.summary || data.summary.total_decisions === 0) {
    body = (
      <div className="card">
        <p className="text-body-sm text-text-muted">No data yet.</p>
      </div>
    )
  } else {
    const summary = data.summary
    const riskDistribution = data.risk_distribution || {}
    const riskTotal = Object.values(riskDistribution).reduce(
      (sum, n) => sum + (Number(n) || 0),
      0
    )
    const riskRows = riskLevels
      .map((lvl) => ({
        ...lvl,
        count: Number(riskDistribution[lvl.key]) || 0,
      }))
      .filter((row) => row.count > 0)
    const chartKeys = data.charts ? Object.keys(data.charts) : []
    const hasCharts = chartKeys.length > 0

    const metricCards = [
      {
        label: "FINANCIAL IMPACT",
        value: formatCurrency(summary.total_financial_impact),
        icon: DollarSign,
        iconBg: "bg-success/10",
        iconColor: "text-success",
      },
      {
        label: "DECISIONS MADE",
        value: formatNumber(summary.total_decisions),
        icon: Target,
        iconBg: "bg-primary/10",
        iconColor: "text-primary",
      },
      {
        label: "APPROVAL RATE",
        value: `${summary.approval_rate.toFixed(1)}%`,
        icon: TrendingUp,
        iconBg: "bg-info/10",
        iconColor: "text-info",
      },
      {
        label: "AVG DECISION TIME",
        value: `${summary.avg_decision_time_minutes.toFixed(1)} min`,
        icon: Clock,
        iconBg: "bg-warning/10",
        iconColor: "text-warning",
      },
    ]

    body = (
      <>
        <div className="grid grid-cols-4 gap-4 mb-6">
          {metricCards.map((m) => {
            const Icon = m.icon
            return (
              <div key={m.label} className="card">
                <div className="flex items-center gap-3 mb-3">
                  <div className={`w-9 h-9 rounded-button ${m.iconBg} flex items-center justify-center`}>
                    <Icon className={`w-4 h-4 ${m.iconColor}`} />
                  </div>
                  <span className="label-caps">{m.label}</span>
                </div>
                <div className="font-display text-data-lg text-text-primary">{m.value}</div>
              </div>
            )
          })}
        </div>

        <div className="card mb-6">
          <h3 className="label-caps mb-4">Risk Distribution</h3>
          {riskRows.length > 0 ? (
            <div className="table-container">
              <table className="table">
                <thead>
                  <tr>
                    <th>RISK LEVEL</th>
                    <th>COUNT</th>
                    <th>SEVERITY</th>
                    <th>SHARE OF TOTAL</th>
                  </tr>
                </thead>
                <tbody>
                  {riskRows.map((row) => (
                    <tr key={row.key}>
                      <td className="text-body-md text-text-primary font-medium">{row.label}</td>
                      <td className="font-mono text-data-sm text-text-secondary">{formatNumber(row.count)}</td>
                      <td><span className={row.severityClass}>{row.label.toUpperCase()}</span></td>
                      <td>
                        <div className="flex items-center gap-3">
                          <div className="w-24 h-1.5 rounded-full bg-surface-3 overflow-hidden">
                            <div
                              className={`h-full rounded-full ${row.barColor}`}
                              style={{ width: `${riskTotal > 0 ? (row.count / riskTotal) * 100 : 0}%` }}
                            />
                          </div>
                          <span className="font-mono text-data-sm text-text-secondary">
                            {riskTotal > 0 ? ((row.count / riskTotal) * 100).toFixed(1) : "0.0"}%
                          </span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-body-sm text-text-muted">No risk data available</p>
          )}
        </div>

        <div className="card">
          <h3 className="label-caps mb-4">Charts</h3>
          {hasCharts ? (
            <p className="text-body-sm text-text-muted">
              Backend returned chart data ({chartKeys.join(", ")}) but no client-side renderer is configured. Raw data is not rendered to avoid fabricated visuals.
            </p>
          ) : (
            <p className="text-body-sm text-text-muted">Charts data unavailable from backend.</p>
          )}
        </div>
      </>
    )
  }

  return (
    <Shell
      title="Performance Intelligence"
      subtitle="Real-time monitoring of AI operational efficiency and financial impact."
      actions={actions}
    >
      {body}
    </Shell>
  )
}