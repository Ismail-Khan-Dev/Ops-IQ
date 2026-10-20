"use client"

import { cn, getRiskColor, getRiskTextColor, formatScore } from "@/lib/utils"

interface RiskScoreProps {
  score: number
  showBar?: boolean
  showLabel?: boolean
  className?: string
}

export function RiskScore({ score, showBar = true, showLabel = false, className }: RiskScoreProps) {
  return (
    <div className={cn("flex items-center gap-2", className)}>
      {showBar && (
        <div className="risk-bar">
          <div
            className={cn("risk-bar-fill", getRiskColor(score))}
            style={{ width: `${score * 100}%` }}
          />
        </div>
      )}
      <span className={cn("font-mono text-data-sm", getRiskTextColor(score))}>
        {showLabel && "Risk "}
        {formatScore(score)}
      </span>
    </div>
  )
}
