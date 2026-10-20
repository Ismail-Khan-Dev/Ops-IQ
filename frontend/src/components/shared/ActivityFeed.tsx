"use client"

import { cn, formatTimestamp, getAgentDotColor, getAgentColor, getConfidenceColor } from "@/lib/utils"
import type { Activity } from "@/types/api"

interface ActivityFeedProps {
  activities: Activity[]
  maxItems?: number
}

export function ActivityFeed({ activities, maxItems = 50 }: ActivityFeedProps) {
  const displayActivities = activities.slice(0, maxItems)

  return (
    <div className="space-y-0.5">
      {displayActivities.map((activity, index) => (
        <div
          key={activity.id}
          className="flex items-start gap-3 p-3 rounded-lg hover:bg-surface-2 transition-colors fade-in"
          style={{ animationDelay: `${index * 50}ms` }}
        >
          {/* Agent dot */}
          <div className="mt-1.5">
            <div className={cn("w-2 h-2 rounded-full", getAgentDotColor(activity.agent))} />
          </div>

          {/* Content */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className={cn("text-sm font-medium", getAgentColor(activity.agent))}>
                {activity.agent.replace(/_/g, " ").replace(/\b\w/g, l => l.toUpperCase())}
              </span>
              <span className="text-sm text-text-2">
                {activity.action}
              </span>
            </div>
            <div className="mt-1 flex items-center gap-3">
              <span className="font-mono text-data-xs text-indigo">
                {activity.description}
              </span>
            </div>
          </div>

          {/* Right side */}
          <div className="flex flex-col items-end gap-1">
            {activity.confidence !== undefined && (
              <span className={cn("confidence-pill", getConfidenceColor(activity.confidence))}>
                {Math.round(activity.confidence * 100)}%
              </span>
            )}
            <span className="text-[11px] text-text-3">
              {formatTimestamp(activity.timestamp)}
            </span>
          </div>
        </div>
      ))}

      {displayActivities.length === 0 && (
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <div className="w-12 h-12 rounded-full bg-surface-3 flex items-center justify-center mb-3">
            <span className="text-2xl">📡</span>
          </div>
          <p className="text-sm text-text-2">No activity yet</p>
          <p className="text-xs text-text-3 mt-1">Agent events will appear here in real-time</p>
        </div>
      )}
    </div>
  )
}
