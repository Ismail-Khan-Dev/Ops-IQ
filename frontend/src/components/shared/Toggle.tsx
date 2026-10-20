"use client"

interface ToggleProps {
  enabled: boolean
  onToggle: () => void
  label?: string
}

export default function Toggle({ enabled, onToggle, label }: ToggleProps) {
  return (
    <button
      onClick={onToggle}
      role="switch"
      aria-checked={enabled}
      aria-label={label}
      className={`relative w-11 h-6 rounded-full transition-colors duration-200 ${
        enabled ? "bg-primary" : "bg-surface-3"
      }`}
    >
      <div
        className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-transform duration-200 ${
          enabled ? "left-6" : "left-1"
        }`}
      />
    </button>
  )
}
