export default function Loading() {
  return (
    <div className="min-h-screen bg-void flex items-center justify-center p-6">
      <div className="w-full max-w-md space-y-6">
        <div className="text-center space-y-3">
          <div className="mx-auto w-14 h-14 rounded-xl bg-surface-3 animate-pulse" />
          <div className="mx-auto w-48 h-4 rounded bg-surface-3 animate-pulse" />
        </div>
        <div className="space-y-3">
          <div className="h-12 rounded-lg bg-surface-3 animate-pulse" />
          <div className="h-12 rounded-lg bg-surface-3 animate-pulse" />
        </div>
      </div>
    </div>
  )
}
