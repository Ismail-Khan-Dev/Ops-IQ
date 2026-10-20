"use client"

import {
  AlertCircle,
  CheckCircle,
  ExternalLink,
  RefreshCw,
} from "lucide-react"
import Shell from "@/components/layout/Shell"
import { useShopifyStatus, useShopifySync } from "@/lib/hooks"

export default function ShopifyPage() {
  const { data: status, isLoading, isError } = useShopifyStatus()
  const { mutate: syncNow, isPending: isSyncing } = useShopifySync()

  const configured = status?.configured ?? null
  const shopDomain = status?.shop_domain ?? null
  const apiVersion = status?.api_version ?? null
  const webhookTopics = status?.webhook_topics ?? []

  const loading = isLoading
  const placeholder = loading ? "…" : "—"

  return (
    <Shell
      title="Shopify Integration"
      subtitle="Monitor and manage your connected Shopify store."
    >
      <div className="space-y-6 max-w-6xl">
        {isError && (
          <div className="flex items-center gap-2 p-3 rounded-lg bg-danger-light border border-danger/20">
            <AlertCircle className="w-4 h-4 text-danger shrink-0" />
            <span className="text-sm text-danger">
              Shopify status endpoint unreachable — no data to display.
            </span>
          </div>
        )}

        <div
          className={`card border-l-4 ${
            configured ? "border-l-success" : "border-l-warning"
          }`}
        >
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-4">
              <div className="relative">
                <div
                  className={`w-14 h-14 rounded-card ${
                    configured
                      ? "bg-success/10"
                      : "bg-warning/10"
                  } flex items-center justify-center`}
                >
                  {configured ? (
                    <CheckCircle className="w-7 h-7 text-success" />
                  ) : (
                    <AlertCircle className="w-7 h-7 text-warning" />
                  )}
                </div>
                {configured && (
                  <span className="absolute -top-1 -right-1 flex h-4 w-4">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-success opacity-40" />
                    <span className="relative inline-flex rounded-full h-4 w-4 bg-success" />
                  </span>
                )}
              </div>
              <div>
                <h3 className="font-display text-display-md text-text-primary">
                  {loading
                    ? "Checking connection…"
                    : configured
                      ? "Connected to Shopify"
                      : "Shopify not configured"}
                </h3>
                <div className="flex items-center gap-2 mt-1">
                  {configured && shopDomain ? (
                    <>
                      <span className="text-body-md text-text-secondary font-mono">
                        {shopDomain}
                      </span>
                      <a
                        href={`https://${shopDomain}/admin`}
                        target="_blank"
                        rel="noreferrer"
                        className="text-primary hover:text-primary-hover transition-colors"
                      >
                        <ExternalLink className="w-3.5 h-3.5" />
                      </a>
                    </>
                  ) : (
                    <span className="text-body-md text-text-secondary">
                      {loading
                        ? "…"
                        : "Set SHOPIFY_SHOP_DOMAIN and SHOPIFY_ACCESS_TOKEN to connect."}
                    </span>
                  )}
                </div>
              </div>
            </div>
            <button
              className="btn-primary"
              onClick={() => syncNow(undefined)}
              disabled={isSyncing}
            >
              <RefreshCw
                className={`w-4 h-4 ${isSyncing ? "animate-spin" : ""}`}
              />{" "}
              {isSyncing ? "Syncing..." : "Sync Now"}
            </button>
          </div>

          <div className="grid grid-cols-2 gap-6 mt-6 pt-6 border-t border-border">
            <div>
              <div className="label-caps mb-1.5">Shop Domain</div>
              <span className="font-mono text-data-md text-text-primary">
                {configured && shopDomain ? shopDomain : placeholder}
              </span>
            </div>
            <div>
              <div className="label-caps mb-1.5">API Version</div>
              <span className="font-mono text-data-md text-text-primary">
                {apiVersion ?? placeholder}
              </span>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h3 className="label-caps">Webhook Topics</h3>
            {webhookTopics.length > 0 && (
              <span className="badge badge-info">{webhookTopics.length}</span>
            )}
          </div>
          {loading ? (
            <div className="py-6 text-center text-sm text-text-muted">
              Loading…
            </div>
          ) : webhookTopics.length === 0 ? (
            <div className="py-6 text-center text-sm text-text-muted">
              None configured
            </div>
          ) : (
            <div className="flex flex-wrap gap-2">
              {webhookTopics.map((topic) => (
                <span key={topic} className="badge badge-info">
                  {topic}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </Shell>
  )
}