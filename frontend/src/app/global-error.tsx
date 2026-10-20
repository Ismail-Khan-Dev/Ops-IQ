"use client"

import { useEffect } from "react"
import { AlertTriangle, RefreshCw, Home } from "lucide-react"
import Link from "next/link"

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    console.error("[GlobalError]", error)
  }, [error])

  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-gray-950 font-body antialiased">
        <div className="flex min-h-screen items-center justify-center p-8">
          <div className="w-full max-w-lg rounded-2xl border border-red-500/20 bg-gray-900/90 p-10 text-center backdrop-blur-xl">
            <div className="mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-full bg-red-500/10 ring-1 ring-red-500/20">
              <AlertTriangle className="h-10 w-10 text-red-400" />
            </div>

            <h1 className="mb-3 text-2xl font-bold text-white">
              Application Error
            </h1>
            <p className="mb-2 text-sm text-gray-400">
              A critical error occurred and the page could not be rendered.
            </p>
            {error.digest && (
              <p className="mb-6 font-mono text-xs text-gray-500">
                Error ID: {error.digest}
              </p>
            )}

            <div className="flex items-center justify-center gap-4">
              <button
                onClick={reset}
                className="flex items-center gap-2 rounded-xl bg-indigo-600 px-6 py-3 text-sm font-semibold text-white hover:bg-indigo-500 transition-all duration-200 shadow-lg shadow-indigo-500/20"
              >
                <RefreshCw className="h-4 w-4" />
                Reload Page
              </button>
              <Link
                href="/"
                className="flex items-center gap-2 rounded-xl border border-gray-700 bg-gray-800 px-6 py-3 text-sm font-semibold text-gray-300 hover:bg-gray-700 transition-all duration-200"
              >
                <Home className="h-4 w-4" />
                Dashboard
              </Link>
            </div>

            <p className="mt-8 text-xs text-gray-600">
              If this persists, check the server logs or contact support.
            </p>
          </div>
        </div>
      </body>
    </html>
  )
}
