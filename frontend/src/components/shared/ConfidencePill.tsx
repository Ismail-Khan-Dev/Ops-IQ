"use client"

import { cn, getConfidenceColor, formatPercent } from "@/lib/utils"

interface ConfidencePillProps {
  value: number
  showLabel?: boolean
  className?: string
}

export function ConfidencePill({ value, showLabel = false, className }: ConfidencePillProps) {
  return (
    <span
      className={cn(
        "confidence-pill",
        getConfidenceColor(value),
        className
      )}
    >
      {showLabel && "AI "}
      {formatPercent(value)}
    </span>
  )
}
