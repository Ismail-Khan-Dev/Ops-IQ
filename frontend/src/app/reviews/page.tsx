"use client"

import { useState } from "react"
import { Search, Star, MessageSquare, ThumbsUp, ThumbsDown } from "lucide-react"
import Shell from "@/components/layout/Shell"
import { cn } from "@/lib/utils"
import { useReviews } from "@/lib/hooks"

const filters = ["All Reviews", "Positive", "Neutral", "Negative"]

function sentimentClass(sentiment: string) {
  switch (sentiment.toUpperCase()) {
    case "POSITIVE":
      return "badge-success"
    case "NEGATIVE":
      return "badge-danger"
    case "NEUTRAL":
      return "badge-info"
    default:
      return "badge-muted"
  }
}

function StarRating({ rating }: { rating: number }) {
  return (
    <div className="flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map((s) => (
        <Star
          key={s}
          className={cn(
            "w-3.5 h-3.5",
            s <= rating ? "text-warning fill-warning" : "text-surface-3"
          )}
        />
      ))}
    </div>
  )
}

export default function ReviewsPage() {
  const [activeFilter, setActiveFilter] = useState("All Reviews")
  const [searchQuery, setSearchQuery] = useState("")
  const { data, isLoading, isError } = useReviews()

  const reviews = data ?? []

  const filtered = reviews.filter((review) => {
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      if (
        !review.author.toLowerCase().includes(q) &&
        !review.content.toLowerCase().includes(q)
      )
        return false
    }
    if (activeFilter === "Positive") return review.sentiment.toUpperCase() === "POSITIVE"
    if (activeFilter === "Neutral") return review.sentiment.toUpperCase() === "NEUTRAL"
    if (activeFilter === "Negative") return review.sentiment.toUpperCase() === "NEGATIVE"
    return true
  })

  const total = reviews.length
  const avgRating =
    total > 0 ? reviews.reduce((sum, r) => sum + r.rating, 0) / total : 0
  const positive = reviews.filter((r) => r.sentiment.toUpperCase() === "POSITIVE").length
  const neutral = reviews.filter((r) => r.sentiment.toUpperCase() === "NEUTRAL").length
  const negative = reviews.filter((r) => r.sentiment.toUpperCase() === "NEGATIVE").length

  const metricCards = [
    {
      label: "Total Reviews",
      value: total > 0 ? total.toLocaleString() : "—",
      icon: MessageSquare,
      color: "bg-primary/15",
      iconColor: "text-primary",
    },
    {
      label: "Avg Rating",
      value: total > 0 ? avgRating.toFixed(1) : "—",
      suffix: total > 0 ? "/5" : undefined,
      icon: Star,
      color: "bg-warning/15",
      iconColor: "text-warning",
    },
    {
      label: "Positive",
      value: total > 0 ? positive.toLocaleString() : "—",
      icon: ThumbsUp,
      color: "bg-success/15",
      iconColor: "text-success",
    },
    {
      label: "Negative",
      value: total > 0 ? negative.toLocaleString() : "—",
      icon: ThumbsDown,
      color: "bg-danger/15",
      iconColor: "text-danger",
    },
  ]

  return (
    <Shell
      title="Review Intelligence"
      subtitle="AI-powered review monitoring, sentiment analysis, and automated response orchestration."
    >
      <div className="space-y-6">
        <div className="grid grid-cols-4 gap-4">
          {metricCards.map((card) => {
            const Icon = card.icon
            return (
              <div key={card.label} className="card group hover:border-border-bright transition-all duration-150">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="label-caps mb-2">{card.label}</div>
                    <div className="font-display text-display-md text-text-primary">
                      {card.value}
                      {card.suffix && (
                        <span className="text-text-muted text-body-md font-normal">{card.suffix}</span>
                      )}
                    </div>
                  </div>
                  <div className={cn("w-9 h-9 rounded-lg flex items-center justify-center", card.color)}>
                    <Icon className={cn("w-4 h-4", card.iconColor)} />
                  </div>
                </div>
              </div>
            )
          })}
        </div>

        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-1 bg-surface rounded-card p-1 border border-border">
            {filters.map((filter) => (
              <button
                key={filter}
                onClick={() => setActiveFilter(filter)}
                className={cn(
                  "px-4 py-2 rounded-button text-sm font-medium transition-all duration-200",
                  activeFilter === filter
                    ? "bg-primary text-white shadow-lg shadow-primary/20"
                    : "text-text-secondary hover:text-text-primary hover:bg-surface-2"
                )}
              >
                {filter}
              </button>
            ))}
          </div>

          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
            <input
              type="text"
              placeholder="Search reviews..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10 pr-4 py-2.5 rounded-button bg-surface border border-border text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-primary/30 transition-colors w-72"
            />
          </div>
        </div>

        <div className="card p-0 overflow-hidden">
          <div className="table-container">
            <table className="table">
              <thead>
                <tr className="border-b border-border">
                  <th className="label-caps px-5 py-4 text-left">Review ID</th>
                  <th className="label-caps px-5 py-4 text-left">Customer</th>
                  <th className="label-caps px-5 py-4 text-center">Rating</th>
                  <th className="label-caps px-5 py-4 text-center">Sentiment</th>
                  <th className="label-caps px-5 py-4 text-left">Review Text</th>
                  <th className="label-caps px-5 py-4 text-right">Date</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr>
                    <td colSpan={6} className="px-5 py-8 text-center text-sm text-text-muted">
                      Loading reviews...
                    </td>
                  </tr>
                ) : isError ? (
                  <tr>
                    <td colSpan={6} className="px-5 py-8 text-center text-sm text-text-muted">
                      Reviews endpoint is not yet available on the backend.
                    </td>
                  </tr>
                ) : filtered.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-5 py-8 text-center text-sm text-text-muted">
                      No reviews match the current filters.
                    </td>
                  </tr>
                ) : (
                  filtered.map((review) => (
                    <tr key={review.id} className="group transition-colors">
                      <td className="px-5 py-4">
                        <span className="font-mono text-data-sm text-primary">{review.id}</span>
                      </td>
                      <td className="px-5 py-4">
                        <span className="text-sm font-medium text-text-primary">{review.author}</span>
                      </td>
                      <td className="px-5 py-4 text-center">
                        <StarRating rating={review.rating} />
                      </td>
                      <td className="px-5 py-4 text-center">
                        <span className={cn("badge", sentimentClass(review.sentiment))}>
                          {review.sentiment}
                        </span>
                      </td>
                      <td className="px-5 py-4 max-w-[320px]">
                        <span className="text-sm text-text-secondary line-clamp-2">{review.content}</span>
                      </td>
                      <td className="px-5 py-4 text-right">
                        <span className="font-mono text-data-sm text-text-secondary">
                          {new Date(review.created_at).toLocaleDateString()}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-2">
              <div className="dot-green" />
              <span className="text-sm text-text-secondary">
                Positive: <span className="font-mono text-data-sm text-success">{positive}</span>
              </span>
            </div>
            <div className="flex items-center gap-2">
              <div className="dot-amber" />
              <span className="text-sm text-text-secondary">
                Neutral: <span className="font-mono text-data-sm text-warning">{neutral}</span>
              </span>
            </div>
            <div className="flex items-center gap-2">
              <div className="dot-red" />
              <span className="text-sm text-text-secondary">
                Negative: <span className="font-mono text-data-sm text-danger">{negative}</span>
              </span>
            </div>
          </div>

          <span className="text-sm text-text-muted">
            Showing <span className="text-text-secondary font-medium">{filtered.length}</span> of{" "}
            <span className="text-text-secondary font-medium">{total}</span> reviews
          </span>
        </div>
      </div>
    </Shell>
  )
}
