import Link from "next/link"
import { AlertCircle, ArrowLeft } from "lucide-react"

export default function NotFound() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-950 p-8">
      <div className="w-full max-w-md text-center">
        <div className="mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-full bg-gray-800/80 ring-1 ring-gray-700">
          <AlertCircle className="h-10 w-10 text-gray-500" />
        </div>

        <h1 className="mb-3 text-6xl font-bold text-white">404</h1>
        <h2 className="mb-3 text-xl font-semibold text-gray-200">
          Page Not Found
        </h2>
        <p className="mb-8 text-sm text-gray-500">
          The page you&apos;re looking for doesn&apos;t exist or has been moved.
        </p>

        <Link
          href="/"
          className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-6 py-3 text-sm font-semibold text-white hover:bg-indigo-500 transition-all duration-200 shadow-lg shadow-indigo-500/20"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Dashboard
        </Link>
      </div>
    </div>
  )
}
