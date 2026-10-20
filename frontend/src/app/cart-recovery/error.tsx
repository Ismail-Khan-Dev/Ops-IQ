"use client"

import { AlertTriangle, RefreshCw } from "lucide-react"

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  return (
    <div className="min-h-[400px] flex items-center justify-center p-8">
      <div className="card max-w-md w-full text-center">
        <div className="w-12 h-12 rounded-full bg-danger/15 flex items-center justify-center mx-auto mb-4">
          <AlertTriangle className="w-6 h-6 text-danger" />
        </div>
        <h2 className="font-display text-lg font-semibold text-text-primary mb-2">
          Failed to load this page
        </h2>
        <p className="text-sm text-text-secondary mb-1">
          {error?.message || "An unexpected error occurred"}
        </p>
        <p className="text-xs text-text-muted mb-6 font-mono">
          {error?.digest && `Error ID: ${error.digest}`}
        </p>
        <button onClick={reset} className="btn-primary">
          <RefreshCw className="w-4 h-4" />
          Try Again
        </button>
      </div>
    </div>
  )
}
