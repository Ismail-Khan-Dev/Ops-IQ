"use client"

import { useState } from "react"
import { Search, AlertTriangle } from "lucide-react"
import Shell from "@/components/layout/Shell"
import { useOrders } from "@/lib/hooks"
import { cn, formatCurrency, formatPercent, getRiskColor } from "@/lib/utils"

const filters = ["All Orders", "Pending Review", "Flagged", "Completed"]

function orderBadge(status: string): string {
  const s = status.toLowerCase()
  if (s.includes("flagged")) return "badge-danger"
  if (s.includes("pending")) return "badge-warning"
  if (s.includes("processing")) return "badge-primary"
  if (s.includes("completed") || s.includes("delivered") || s.includes("shipped")) return "badge-success"
  if (s.includes("cancel")) return "badge-muted"
  return "badge-info"
}

export default function OrdersPage() {
  const [activeFilter, setActiveFilter] = useState("All Orders")
  const [searchQuery, setSearchQuery] = useState("")
  const { data, isLoading, isError } = useOrders()

  const orders = data?.orders ?? []

  const filteredOrders = orders.filter((order) => {
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      if (!order.id.toLowerCase().includes(q) && !order.customer.toLowerCase().includes(q)) {
        return false
      }
    }
    if (activeFilter === "Pending Review") return order.status.toLowerCase().includes("pending")
    if (activeFilter === "Flagged") return order.status.toLowerCase().includes("flagged")
    if (activeFilter === "Completed") {
      return (
        order.status.toLowerCase().includes("completed") ||
        order.status.toLowerCase().includes("delivered")
      )
    }
    return true
  })

  return (
    <Shell
      title="Order Intelligence"
      subtitle="AI-powered order tracking, fraud detection, and fulfillment optimization."
    >
      <div className="space-y-6">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-1 bg-surface-2 rounded-card p-1 border border-border">
            {filters.map((filter) => (
              <button
                key={filter}
                onClick={() => setActiveFilter(filter)}
                className={cn(
                  "px-4 py-2 rounded-button text-sm font-medium transition-all duration-200",
                  activeFilter === filter
                    ? "bg-primary text-white shadow-sm"
                    : "text-text-secondary hover:text-text-primary hover:bg-surface-3"
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
              placeholder="Search orders..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10 pr-4 py-2.5 rounded-button bg-white border border-border text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/20 transition-all w-72"
            />
          </div>
        </div>

        <div className="bg-white rounded-card shadow-card border border-border overflow-hidden">
          {isError ? (
            <div className="m-4 flex items-center gap-2 p-3 rounded-lg bg-danger-light border border-danger/20">
              <AlertTriangle className="w-4 h-4 text-danger shrink-0" />
              <span className="text-sm text-danger">
                Orders endpoint is not yet available on the backend.
              </span>
            </div>
          ) : isLoading ? (
            <div className="p-8 text-center text-sm text-text-secondary">Loading...</div>
          ) : (
            <div className="table-container">
              <table className="table">
                <thead>
                  <tr className="border-b border-border">
                    <th className="label-caps px-5 py-4 text-left">Order ID</th>
                    <th className="label-caps px-5 py-4 text-left">Customer</th>
                    <th className="label-caps px-5 py-4 text-right">Amount</th>
                    <th className="label-caps px-5 py-4 text-center">Status</th>
                    <th className="label-caps px-5 py-4 text-left">Fraud Score</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredOrders.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="px-5 py-8 text-center text-sm text-text-secondary">
                        No orders found.
                      </td>
                    </tr>
                  ) : (
                    filteredOrders.map((order) => (
                      <tr key={order.id} className="border-b border-border last:border-b-0 hover:bg-surface-2 transition-colors">
                        <td className="px-5 py-4">
                          <span className="font-mono text-data-sm text-primary">{order.id}</span>
                        </td>
                        <td className="px-5 py-4">
                          <span className="text-sm font-medium text-text-primary">{order.customer}</span>
                        </td>
                        <td className="px-5 py-4 text-right">
                          <span className="font-mono text-data-sm text-text-primary">
                            {formatCurrency(order.total)}
                          </span>
                        </td>
                        <td className="px-5 py-4 text-center">
                          <span className={cn("badge", orderBadge(order.status))}>{order.status}</span>
                        </td>
                        <td className="px-5 py-4">
                          <div className="flex items-center gap-3 min-w-[140px]">
                            <div className="risk-bar flex-1">
                              <div
                                className={cn("risk-bar-fill", getRiskColor(order.fraud_score))}
                                style={{ width: `${Math.max(0, Math.min(1, order.fraud_score)) * 100}%` }}
                              />
                            </div>
                            <span className="font-mono text-data-sm text-text-secondary w-10 text-right">
                              {formatPercent(order.fraud_score)}
                            </span>
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {data && !isLoading && !isError && filteredOrders.length > 0 && (
          <div className="flex items-center justify-end">
            <span className="text-sm text-text-muted">
              Showing <span className="text-text-secondary font-medium">{filteredOrders.length}</span> of{" "}
              <span className="text-text-secondary font-medium">{data.total}</span> orders
            </span>
          </div>
        )}
      </div>
    </Shell>
  )
}