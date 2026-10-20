"use client"

import { useState } from "react"
import { MessageSquare, CheckCircle2, Clock, AlertTriangle } from "lucide-react"
import Shell from "@/components/layout/Shell"
import { cn } from "@/lib/utils"
import { useSupportTickets, useSupportAnalytics } from "@/lib/hooks"
import type { SupportTicket } from "@/lib/api"

const filters = ["All Tickets", "Escalated", "AI Resolved", "Pending"]

interface TicketDisplay {
  id: string
  customer: string
  issue: string
  issueClass: string
  priority: string
  priorityClass: string
  status: string
  statusClass: string
}

function getPriorityClass(p: string) {
  if (p === "critical" || p === "high") return "badge-danger"
  if (p === "medium") return "badge-warning"
  return "badge-muted"
}

function getStatusClass(s: string) {
  if (s === "resolved") return "badge-success"
  if (s === "escalated" || s === "open") return "badge-danger"
  if (s === "pending") return "badge-warning"
  return "badge-info"
}

function mapTicket(t: SupportTicket): TicketDisplay {
  return {
    id: t.id,
    customer: t.customer_name || t.customer_email,
    issue: t.subject || t.category,
    issueClass: "badge-primary",
    priority: t.priority.toUpperCase(),
    priorityClass: getPriorityClass(t.priority),
    status: t.status.toUpperCase(),
    statusClass: getStatusClass(t.status),
  }
}

function formatNumber(value: number | null | undefined) {
  return typeof value === "number" ? value.toLocaleString() : "—"
}

function formatHours(value: number | null | undefined) {
  return typeof value === "number" ? `${value.toFixed(1)}h` : "—"
}

function formatScore(value: number | null | undefined) {
  return typeof value === "number" ? `${value.toFixed(1)}/5` : "—"
}

export default function SupportPage() {
  const [activeFilter, setActiveFilter] = useState("All Tickets")
  const { data: ticketsData, isLoading: ticketsLoading, isError: ticketsError } = useSupportTickets()
  const { data: analyticsData } = useSupportAnalytics()

  const tickets: TicketDisplay[] = (ticketsData?.tickets ?? []).map(mapTicket)

  const metrics = [
    {
      label: "TOTAL TICKETS",
      value: formatNumber(analyticsData?.total_tickets),
      icon: MessageSquare,
      iconBg: "bg-primary/10",
      iconColor: "text-primary",
    },
    {
      label: "OPEN TICKETS",
      value: formatNumber(analyticsData?.open_tickets),
      icon: CheckCircle2,
      iconBg: "bg-success/10",
      iconColor: "text-success",
    },
    {
      label: "AVG RESPONSE TIME",
      value: formatHours(analyticsData?.avg_response_time_hours),
      icon: Clock,
      iconBg: "bg-info/10",
      iconColor: "text-info",
    },
    {
      label: "SATISFACTION",
      value: formatScore(analyticsData?.satisfaction_score),
      icon: AlertTriangle,
      iconBg: "bg-warning/10",
      iconColor: "text-warning",
    },
  ]

  const filteredTickets = tickets.filter((ticket) => {
    const status = ticket.status.toLowerCase()
    if (activeFilter === "Escalated") return status === "escalated"
    if (activeFilter === "AI Resolved") return status === "resolved"
    if (activeFilter === "Pending") return status === "pending"
    return true
  })

  const shownTotal = ticketsData?.total ?? tickets.length

  return (
    <Shell
      title="Customer Support"
      subtitle="AI-powered ticket orchestration and automated customer resolution workflows."
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

        <div className="grid grid-cols-4 gap-4">
          {metrics.map((m) => {
            const Icon = m.icon
            return (
              <div key={m.label} className="card">
                <div className="flex items-center gap-3 mb-3">
                  <div className={`w-9 h-9 rounded-button ${m.iconBg} flex items-center justify-center`}>
                    <Icon className={`w-4 h-4 ${m.iconColor}`} />
                  </div>
                  <span className="label-caps">{m.label}</span>
                </div>
                <div className="font-display text-data-lg text-text-primary">{m.value}</div>
              </div>
            )
          })}
        </div>

        <div className="card p-0 overflow-hidden">
          <div className="table-container">
            {ticketsLoading ? (
              <div className="p-8 text-center text-sm text-text-secondary">Loading…</div>
            ) : ticketsError ? (
              <div className="p-8 text-center text-sm text-text-secondary">
                Support endpoint unreachable — no data to display.
              </div>
            ) : filteredTickets.length === 0 ? (
              <div className="p-8 text-center text-sm text-text-secondary">
                {tickets.length === 0 ? "No tickets to display." : "No tickets match this filter."}
              </div>
            ) : (
              <table className="table">
                <thead>
                  <tr className="border-b border-border">
                    <th className="label-caps px-5 py-4 text-left">TICKET ID</th>
                    <th className="label-caps px-5 py-4 text-left">CUSTOMER</th>
                    <th className="label-caps px-5 py-4 text-left">ISSUE TYPE</th>
                    <th className="label-caps px-5 py-4 text-center">PRIORITY</th>
                    <th className="label-caps px-5 py-4 text-center">STATUS</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredTickets.map((ticket) => (
                    <tr key={ticket.id} className="group transition-colors">
                      <td className="px-5 py-4">
                        <span className="font-mono text-data-sm text-primary">{ticket.id}</span>
                      </td>
                      <td className="px-5 py-4">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-full bg-surface-3 flex items-center justify-center shrink-0">
                            <span className="text-xs font-medium text-text-secondary">
                              {ticket.customer.split(" ").map((n) => n[0]).join("")}
                            </span>
                          </div>
                          <span className="text-sm font-medium text-text-primary">{ticket.customer}</span>
                        </div>
                      </td>
                      <td className="px-5 py-4">
                        <span className={ticket.issueClass}>{ticket.issue}</span>
                      </td>
                      <td className="px-5 py-4 text-center">
                        <span className={ticket.priorityClass}>{ticket.priority}</span>
                      </td>
                      <td className="px-5 py-4 text-center">
                        <span className={ticket.statusClass}>{ticket.status}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {!ticketsLoading && !ticketsError && tickets.length > 0 && (
          <div className="flex items-center justify-end">
            <span className="text-sm text-text-muted">
              Showing <span className="text-text-secondary font-medium">{filteredTickets.length}</span> of{" "}
              <span className="text-text-secondary font-medium">{shownTotal.toLocaleString()}</span> tickets
            </span>
          </div>
        )}
      </div>
    </Shell>
  )
}