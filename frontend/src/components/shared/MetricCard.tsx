"use client"

import { TrendingUp, TrendingDown, Minus } from "lucide-react"
import { cn, formatNumber, formatCurrency } from "@/lib/utils"

interface MetricCardProps {
  label: string
  value: number | string
  delta?: number
  deltaLabel?: string
  icon: React.ReactNode
  color: string
  format?: "number" | "currency" | "percent"
  prefix?: string
  suffix?: string
}

export function MetricCard({
  label,
  value,
  delta,
  deltaLabel,
  icon,
  color,
  format = "number",
  prefix,
  suffix,
}: MetricCardProps) {
  const formatValue = (val: number | string) => {
    if (typeof val === "string") return val
    switch (format) {
      case "currency":
        return formatCurrency(val)
      case "percent":
        return `${Math.round(val)}%`
      default:
        return formatNumber(val)
    }
  }

  return (
    <div className="card group hover:border-border-bright transition-all duration-150">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="section-label mb-2">{label}</div>
          <div className="metric-value text-display-md text-text-1">
            {prefix}{formatValue(value)}{suffix}
          </div>
          {delta !== undefined && (
            <div className="flex items-center gap-1.5 mt-2">
              {delta > 0 ? (
                <TrendingUp className="w-3 h-3 text-emerald" />
              ) : delta < 0 ? (
                <TrendingDown className="w-3 h-3 text-red" />
              ) : (
                <Minus className="w-3 h-3 text-text-3" />
              )}
              <span
                className={cn(
                  "text-xs font-medium",
                  delta > 0 ? "text-emerald" : delta < 0 ? "text-red" : "text-text-3"
                )}
              >
                {delta > 0 ? "+" : ""}{delta}%
              </span>
              {deltaLabel && (
                <span className="text-xs text-text-3">{deltaLabel}</span>
              )}
            </div>
          )}
        </div>
        <div
          className={cn(
            "w-9 h-9 rounded-lg flex items-center justify-center transition-all duration-150",
            color
          )}
        >
          {icon}
        </div>
      </div>
    </div>
  )
}
