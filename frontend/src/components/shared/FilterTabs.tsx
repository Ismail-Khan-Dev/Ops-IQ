"use client"

import { cn } from "@/lib/utils"

interface FilterTabsProps {
  filters: string[]
  active: string
  onChange: (filter: string) => void
}

export default function FilterTabs({ filters, active, onChange }: FilterTabsProps) {
  return (
    <div className="flex items-center gap-1 bg-surface rounded-card p-1 border border-border w-fit">
      {filters.map((filter) => (
        <button
          key={filter}
          onClick={() => onChange(filter)}
          className={cn(
            "px-4 py-2 rounded-button text-sm font-medium transition-all duration-200",
            active === filter
              ? "bg-primary text-white shadow-lg shadow-primary/20"
              : "text-text-secondary hover:text-text-primary hover:bg-surface-2"
          )}
          aria-pressed={active === filter}
        >
          {filter}
        </button>
      ))}
    </div>
  )
}
