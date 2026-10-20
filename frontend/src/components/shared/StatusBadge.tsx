"use client"

import { cn, getStatusColor } from "@/lib/utils"

interface StatusBadgeProps {
  status: string
  size?: "sm" | "md"
  className?: string
}

export function StatusBadge({ status, size = "sm", className }: StatusBadgeProps) {
  return (
    <span
      className={cn(
        "badge",
        getStatusColor(status),
        size === "sm" ? "text-[10px]" : "text-[11px]",
        className
      )}
    >
      {status}
    </span>
  )
}
