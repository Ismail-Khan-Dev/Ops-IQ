import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount)
}

export function formatNumber(num: number): string {
  return new Intl.NumberFormat('en-US').format(num)
}

export function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`
}

export function formatScore(value: number): string {
  return value.toFixed(2)
}

export function formatTimestamp(date: Date | string): string {
  const d = typeof date === 'string' ? new Date(date) : date
  const now = new Date()
  const diffMs = now.getTime() - d.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays < 7) return `${diffDays}d ago`
  
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

export function getConfidenceColor(confidence: number): string {
  if (confidence >= 0.8) return 'confidence-high'
  if (confidence >= 0.5) return 'confidence-medium'
  return 'confidence-low'
}

export function getConfidenceTextColor(confidence: number): string {
  if (confidence >= 0.8) return 'text-success'
  if (confidence >= 0.5) return 'text-warning'
  return 'text-danger'
}

export function getRiskColor(risk: number): string {
  if (risk < 0.3) return 'bg-success'
  if (risk < 0.7) return 'bg-warning'
  return 'bg-danger'
}

export function getRiskTextColor(risk: number): string {
  if (risk < 0.3) return 'text-success'
  if (risk < 0.7) return 'text-warning'
  return 'text-danger'
}

export function getStatusColor(status: string): string {
  const colors: Record<string, string> = {
    active: 'badge-active',
    paused: 'badge-paused',
    error: 'badge-error',
    processing: 'badge-processing',
    approved: 'badge-approved',
    flagged: 'badge-flagged',
    pending: 'badge-pending',
  }
  return colors[status] || 'badge-pending'
}

export function getAgentColor(agent: string): string {
  const colors: Record<string, string> = {
    fraud_detection: 'text-danger',
    inventory_management: 'text-info',
    price_optimization: 'text-warning',
    review_moderation: 'text-primary',
    marketing_automation: 'text-primary',
    cart_recovery: 'text-success',
    customer_support: 'text-info',
  }
  return colors[agent] || 'text-primary'
}

export function getAgentDotColor(agent: string): string {
  const colors: Record<string, string> = {
    fraud_detection: 'bg-danger',
    inventory_management: 'bg-info',
    price_optimization: 'bg-warning',
    review_moderation: 'bg-primary',
    marketing_automation: 'bg-primary',
    cart_recovery: 'bg-success',
    customer_support: 'bg-info',
  }
  return colors[agent] || 'bg-primary'
}

export function truncate(str: string, length: number): string {
  if (str.length <= length) return str
  return str.slice(0, length) + '...'
}
