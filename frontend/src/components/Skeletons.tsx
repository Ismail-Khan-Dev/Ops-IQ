export function SkeletonCard() {
  return (
    <div className="card animate-pulse">
      <div className="flex items-center gap-3 mb-3">
        <div className="w-10 h-10 rounded-lg bg-surface-3" />
        <div className="flex-1">
          <div className="h-3 w-24 bg-surface-4 rounded mb-2" />
          <div className="h-4 w-16 bg-surface-4 rounded" />
        </div>
      </div>
      <div className="h-2 w-full bg-surface-4 rounded mb-2" />
      <div className="h-2 w-3/4 bg-surface-4 rounded" />
    </div>
  )
}

export function SkeletonTable({ rows = 5, cols = 6 }: { rows?: number; cols?: number }) {
  return (
    <div className="card animate-pulse">
      <div className="flex items-center justify-between mb-4">
        <div className="h-4 w-32 bg-surface-4 rounded" />
        <div className="h-3 w-20 bg-surface-4 rounded" />
      </div>
      <div className="space-y-3">
        {Array.from({ length: rows }).map((_, r) => (
          <div key={r} className="flex gap-4">
            {Array.from({ length: cols }).map((_, c) => (
              <div key={c} className="h-3 bg-surface-4 rounded flex-1" />
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}

export function SkeletonMetric() {
  return (
    <div className="card animate-pulse">
      <div className="h-3 w-20 bg-surface-4 rounded mb-2" />
      <div className="h-6 w-24 bg-surface-4 rounded mb-2" />
      <div className="h-2 w-16 bg-surface-4 rounded" />
    </div>
  )
}

export function SkeletonPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <div className="h-6 w-48 bg-surface-4 rounded mb-2 animate-pulse" />
          <div className="h-3 w-72 bg-surface-4 rounded animate-pulse" />
        </div>
        <div className="flex gap-2">
          <div className="h-8 w-20 bg-surface-4 rounded animate-pulse" />
          <div className="h-8 w-20 bg-surface-4 rounded animate-pulse" />
        </div>
      </div>
      <div className="grid grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <SkeletonMetric key={i} />
        ))}
      </div>
      <SkeletonTable />
    </div>
  )
}
