"use client"

import {
  AlertTriangle,
  DollarSign,
  ShoppingCart,
  TrendingUp,
  Wallet,
} from "lucide-react"
import Shell from "@/components/layout/Shell"
import { useCartRecoveryAnalytics } from "@/lib/hooks"

const formatMoney = (value: number) =>
  `$${value.toLocaleString("en-US", { maximumFractionDigits: 0 })}`

export default function CartRecoveryPage() {
  const { data, isLoading, isError } = useCartRecoveryAnalytics()

  const placeholder = isLoading ? "…" : "—"
  const recoveryRate = data?.recovery_rate ?? null
  const revenueRecovered = data?.total_revenue_recovered ?? null
  const revenueLost = data?.total_revenue_lost ?? null
  const averageCartValue = data?.average_cart_value ?? null

  const metrics = [
    {
      label: "Recovery Rate",
      value:
        recoveryRate === null ? placeholder : `${recoveryRate}%`,
      valueClass: "text-success",
      icon: TrendingUp,
      iconClass: "bg-success-light text-success",
    },
    {
      label: "Revenue Recovered",
      value:
        revenueRecovered === null ? placeholder : formatMoney(revenueRecovered),
      valueClass: "text-success",
      icon: DollarSign,
      iconClass: "bg-success-light text-success",
    },
    {
      label: "Revenue at Risk",
      value: revenueLost === null ? placeholder : formatMoney(revenueLost),
      valueClass: "text-danger",
      icon: Wallet,
      iconClass: "bg-danger-light text-danger",
    },
    {
      label: "Avg Cart Value",
      value:
        averageCartValue === null ? placeholder : formatMoney(averageCartValue),
      valueClass: "text-info",
      icon: ShoppingCart,
      iconClass: "bg-info-light text-info",
    },
  ]

  return (
    <Shell
      title="Cart Recovery"
      subtitle="AI-powered abandoned cart detection and automated recovery."
    >
      <div className="space-y-6">
        {isError && (
          <div className="flex items-center gap-2 p-3 rounded-lg bg-danger-light border border-danger/20">
            <AlertTriangle className="w-4 h-4 text-danger shrink-0" />
            <span className="text-sm text-danger">
              Cart recovery endpoint unreachable — no data to display.
            </span>
          </div>
        )}

        <div className="grid grid-cols-4 gap-4">
          {metrics.map((metric) => {
            const Icon = metric.icon
            return (
              <div key={metric.label} className="card">
                <div className="flex items-center gap-3 mb-3">
                  <div
                    className={`w-9 h-9 rounded-button ${metric.iconClass} flex items-center justify-center`}
                  >
                    <Icon className="w-4 h-4" />
                  </div>
                  <span className="label-caps">{metric.label}</span>
                </div>
                <div className={`font-display text-data-lg ${metric.valueClass}`}>
                  {metric.value}
                </div>
              </div>
            )
          })}
        </div>

        <div className="card">
          <h3 className="label-caps mb-4">Abandoned Carts</h3>
          <div className="py-10 text-center text-sm text-text-muted">
            Abandoned cart list is not yet available from the backend.
          </div>
        </div>
      </div>
    </Shell>
  )
}