"use client"

import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { ShieldCheck } from "lucide-react"
import Shell from "@/components/layout/Shell"
import { cn } from "@/lib/utils"
import { useSecurityEvents } from "@/lib/hooks"
import { securityApi, type SecurityEvent } from "@/lib/api"

const filters = ["All Events", "Critical", "Warning", "Info"]

function severityClass(severity: string) {
  const s = severity.toUpperCase()
  if (s === "CRITICAL" || s === "HIGH") return "badge-danger"
  if (s === "WARNING" || s === "MEDIUM") return "badge-warning"
  if (s === "INFO" || s === "LOW") return "badge-info"
  return "badge-muted"
}

export default function SecurityPage() {
  const [activeFilter, setActiveFilter] = useState("All Events")
  const { data: events, isLoading, isError } = useSecurityEvents()

  const { data: health, isLoading: healthLoading, isError: healthError } = useQuery({
    queryKey: ["security", "health"],
    queryFn: securityApi.health,
    refetchInterval: 30_000,
    staleTime: 15_000,
  })

  const eventList = events ?? []

  const filtered = eventList.filter((event: SecurityEvent) => {
    if (activeFilter === "Critical")
      return event.severity.toUpperCase() === "CRITICAL"
    if (activeFilter === "Warning")
      return event.severity.toUpperCase() === "WARNING"
    if (activeFilter === "Info") return event.severity.toUpperCase() === "INFO"
    return true
  })

  return (
    <Shell
      title="Security Operations"
      subtitle="Real-time threat detection, access control monitoring, and compliance management."
    >
      <div className="space-y-6">
        <div className="flex items-center gap-1 bg-surface rounded-card p-1 border border-border w-fit">
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

        <div className="card">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-9 h-9 rounded-button bg-success/10 flex items-center justify-center">
              <ShieldCheck className="w-4 h-4 text-success" />
            </div>
            <span className="label-caps">Security Service Health</span>
          </div>
          {healthLoading ? (
            <span className="text-sm text-text-muted">Checking security service health...</span>
          ) : healthError || !health ? (
            <span className="text-sm text-text-muted">Security service health unreachable.</span>
          ) : (
            <div className="grid grid-cols-4 gap-4">
              <div>
                <div className="label-caps mb-1">Status</div>
                <span
                  className={cn(
                    "badge",
                    health.status === "healthy" ? "badge-success" : "badge-warning"
                  )}
                >
                  {health.status}
                </span>
              </div>
              <div>
                <div className="label-caps mb-1">RBAC</div>
                <div className="font-mono text-data-sm text-text-primary">{health.rbac}</div>
              </div>
              <div>
                <div className="label-caps mb-1">Audit Logging</div>
                <div className="font-mono text-data-sm text-text-primary">{health.audit_logging}</div>
              </div>
              <div>
                <div className="label-caps mb-1">Rate Limiting</div>
                <div className="font-mono text-data-sm text-text-primary">{health.rate_limiting}</div>
              </div>
            </div>
          )}
        </div>

        <div className="card p-0 overflow-hidden">
          <div className="table-container">
            <table className="table">
              <thead>
                <tr className="border-b border-border">
                  <th className="label-caps px-5 py-4 text-left">EVENT ID</th>
                  <th className="label-caps px-5 py-4 text-left">TIMESTAMP</th>
                  <th className="label-caps px-5 py-4 text-left">EVENT TYPE</th>
                  <th className="label-caps px-5 py-4 text-center">SEVERITY</th>
                  <th className="label-caps px-5 py-4 text-left">SOURCE IP</th>
                  <th className="label-caps px-5 py-4 text-left">DESCRIPTION</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr>
                    <td colSpan={6} className="px-5 py-8 text-center text-sm text-text-muted">
                      Loading security events...
                    </td>
                  </tr>
                ) : isError ? (
                  <tr>
                    <td colSpan={6} className="px-5 py-8 text-center text-sm text-text-muted">
                      Security events endpoint is not yet available on the backend.
                    </td>
                  </tr>
                ) : filtered.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-5 py-8 text-center text-sm text-text-muted">
                      No security events to display.
                    </td>
                  </tr>
                ) : (
                  filtered.map((event) => (
                    <tr key={event.id} className="group transition-colors">
                      <td className="px-5 py-4">
                        <span className="font-mono text-data-sm text-primary">{event.id}</span>
                      </td>
                      <td className="px-5 py-4">
                        <span className="font-mono text-data-sm text-text-secondary">
                          {new Date(event.created_at).toLocaleString()}
                        </span>
                      </td>
                      <td className="px-5 py-4">
                        <span className="text-sm text-text-primary">{event.type}</span>
                      </td>
                      <td className="px-5 py-4 text-center">
                        <span className={cn("badge", severityClass(event.severity))}>
                          {event.severity}
                        </span>
                      </td>
                      <td className="px-5 py-4">
                        <span className="font-mono text-data-sm text-text-secondary">
                          {event.source_ip ?? "—"}
                        </span>
                      </td>
                      <td className="px-5 py-4 max-w-[320px]">
                        <span className="text-sm text-text-secondary line-clamp-2">
                          {event.description}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="flex items-center justify-end">
          <span className="text-sm text-text-muted">
            Showing <span className="text-text-secondary font-medium">{filtered.length}</span> of{" "}
            <span className="text-text-secondary font-medium">{eventList.length}</span> security events
          </span>
        </div>
      </div>
    </Shell>
  )
}