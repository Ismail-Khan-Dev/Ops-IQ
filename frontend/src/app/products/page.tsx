"use client"

import { useState } from "react"
import { Search, AlertTriangle } from "lucide-react"
import Shell from "@/components/layout/Shell"
import { useProducts } from "@/lib/hooks"
import { cn } from "@/lib/utils"

const filters = ["All Products", "Low Stock", "Optimized", "New Arrivals"]

function productBadge(status: string): string {
  const s = status.toLowerCase()
  if (s.includes("out")) return "badge-danger"
  if (s.includes("low")) return "badge-warning"
  if (s.includes("optimal") || s.includes("optimized") || s.includes("in stock")) return "badge-success"
  if (s.includes("excess")) return "badge-info"
  return "badge-muted"
}

export default function ProductsPage() {
  const [activeFilter, setActiveFilter] = useState("All Products")
  const [searchQuery, setSearchQuery] = useState("")
  const { data, isLoading, isError } = useProducts()

  const products = data?.products ?? []

  const filteredProducts = products.filter((product) => {
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      if (!product.id.toLowerCase().includes(q) && !product.title.toLowerCase().includes(q)) {
        return false
      }
    }
    if (activeFilter === "Low Stock") {
      const s = product.status.toLowerCase()
      return s.includes("low") || s.includes("out")
    }
    if (activeFilter === "Optimized") {
      const s = product.status.toLowerCase()
      return s.includes("optimal") || s.includes("optimized")
    }
    if (activeFilter === "New Arrivals") return product.status.toLowerCase().includes("new")
    return true
  })

  return (
    <Shell
      title="Product Catalog"
      subtitle="AI-powered inventory management and catalog optimization."
    >
      <div className="space-y-6">
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
              placeholder="Search products..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10 pr-4 py-2.5 rounded-button bg-surface border border-border text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-primary/30 transition-colors w-72"
            />
          </div>
        </div>

        <div className="card p-0 overflow-hidden">
          {isError ? (
            <div className="m-4 flex items-center gap-2 p-3 rounded-lg bg-danger-light border border-danger/20">
              <AlertTriangle className="w-4 h-4 text-danger shrink-0" />
              <span className="text-sm text-danger">
                Products endpoint is not yet available on the backend.
              </span>
            </div>
          ) : isLoading ? (
            <div className="p-8 text-center text-sm text-text-secondary">Loading...</div>
          ) : (
            <div className="table-container">
              <table className="table">
                <thead>
                  <tr className="border-b border-border">
                    <th className="label-caps px-5 py-4 text-left">SKU</th>
                    <th className="label-caps px-5 py-4 text-left">Product Name</th>
                    <th className="label-caps px-5 py-4 text-right">Stock</th>
                    <th className="label-caps px-5 py-4 text-center">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredProducts.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="px-5 py-8 text-center text-sm text-text-secondary">
                        No products found.
                      </td>
                    </tr>
                  ) : (
                    filteredProducts.map((product) => (
                      <tr key={product.id} className="group transition-colors">
                        <td className="px-5 py-4">
                          <span className="font-mono text-data-sm text-primary">{product.id}</span>
                        </td>
                        <td className="px-5 py-4">
                          <span className="text-sm font-medium text-text-primary">{product.title}</span>
                        </td>
                        <td className="px-5 py-4 text-right">
                          <span
                            className={cn(
                              "font-mono text-data-sm",
                              product.stock === 0
                                ? "text-danger"
                                : product.stock <= 50
                                  ? "text-warning"
                                  : product.stock > 1000
                                    ? "text-info"
                                    : "text-text-primary"
                            )}
                          >
                            {product.stock.toLocaleString()}
                          </span>
                        </td>
                        <td className="px-5 py-4 text-center">
                          <span className={cn("badge", productBadge(product.status))}>
                            {product.status}
                          </span>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {data && !isLoading && !isError && filteredProducts.length > 0 && (
          <div className="flex items-center justify-end">
            <span className="text-sm text-text-muted">
              Showing <span className="text-text-secondary font-medium">{filteredProducts.length}</span> of{" "}
              <span className="text-text-secondary font-medium">{data.total}</span> products
            </span>
          </div>
        )}
      </div>
    </Shell>
  )
}