"use client"

import { useEffect, useState } from "react"
import { Save, CheckCircle, Loader2, AlertTriangle, ShieldAlert, SlidersHorizontal, BadgeDollarSign } from "lucide-react"
import Shell from "@/components/layout/Shell"
import Toggle from "@/components/shared/Toggle"
import { useSettings, useUpdateSettings } from "@/lib/hooks"

export default function SettingsPage() {
  const { data, isLoading, isError } = useSettings()
  const update = useUpdateSettings()
  const [saved, setSaved] = useState(false)

  const [form, setForm] = useState({
    shadow_mode: true,
    fraud_threshold: 70,
    po_limit: 1000,
    pricing_limit: 5,
    reviews_rating_threshold: 4,
  })

  // Hydrate form from the backend once data arrives. Guarded so an
  // identity-unstable data reference (e.g. a memoized transform) can never
  // cause an infinite setForm -> re-render loop.
  useEffect(() => {
    if (data) {
      setForm((prev) => {
        const next = {
          shadow_mode: data.shadow_mode ?? prev.shadow_mode,
          fraud_threshold: data.fraud_threshold ?? prev.fraud_threshold,
          po_limit: data.po_limit ?? prev.po_limit,
          pricing_limit: data.pricing_limit ?? prev.pricing_limit,
          reviews_rating_threshold: data.reviews_rating_threshold ?? prev.reviews_rating_threshold,
        }
        if (
          next.shadow_mode === prev.shadow_mode &&
          next.fraud_threshold === prev.fraud_threshold &&
          next.po_limit === prev.po_limit &&
          next.pricing_limit === prev.pricing_limit &&
          next.reviews_rating_threshold === prev.reviews_rating_threshold
        ) {
          return prev
        }
        return next
      })
    }
  }, [data])

  const handleSave = async () => {
    update.mutate(
      {
        shadow_mode: form.shadow_mode,
        fraud_threshold: form.fraud_threshold,
        po_limit: form.po_limit,
        pricing_limit: form.pricing_limit,
        reviews_rating_threshold: form.reviews_rating_threshold,
      },
      {
        onSuccess: () => {
          setSaved(true)
          setTimeout(() => setSaved(false), 2000)
        },
      }
    )
  }

  const setNum = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.valueAsNumber
    setForm((p) => ({ ...p, [key]: Number.isFinite(value) ? value : p[key] }))
  }

  return (
    <Shell
      title="System Settings"
      subtitle="Configure automation behavior, risk thresholds, and operational limits."
    >
      <div className="space-y-6 max-w-6xl">
        <div className="grid grid-cols-2 gap-6">
          {/* Automation Behavior */}
          <div className="card border-l-4 border-l-primary">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-9 h-9 rounded-button bg-primary/10 flex items-center justify-center">
                <SlidersHorizontal className="w-4 h-4 text-primary" />
              </div>
              <div>
                <h3 className="font-display text-display-sm text-text-primary">
                  Automation Behavior
                </h3>
                <p className="text-body-sm text-text-muted mt-0.5">
                  Control how agents operate across the store
                </p>
              </div>
            </div>

            <div className="space-y-5">
              <div className="flex items-center justify-between p-3 rounded-button bg-surface-2 border border-border">
                <div>
                  <div className="text-body-md text-text-primary font-medium">Shadow Mode</div>
                  <div className="text-body-sm text-text-muted">
                    Preview decisions without executing changes
                  </div>
                </div>
                <Toggle
                  enabled={form.shadow_mode}
                  onToggle={() => setForm((p) => ({ ...p, shadow_mode: !p.shadow_mode }))}
                />
              </div>

              <div>
                <label className="label-caps mb-2 block">Fraud Score Threshold</label>
                <div className="flex items-center gap-3">
                  <input
                    type="range"
                    min={0}
                    max={100}
                    value={form.fraud_threshold}
                    onChange={(e) =>
                      setForm((p) => ({ ...p, fraud_threshold: Number(e.target.value) }))
                    }
                    className="flex-1 accent-primary"
                  />
                  <div className="w-14 px-2 py-2 rounded-button bg-surface-2 border border-border text-center text-body-md text-text-primary font-mono">
                    {form.fraud_threshold}
                  </div>
                </div>
                <p className="text-body-sm text-text-muted mt-1">
                  Flag orders with fraud score at or above this value (0-100)
                </p>
              </div>
            </div>
          </div>

          {/* Risk & Spend Limits */}
          <div className="card border-l-4 border-l-primary">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-9 h-9 rounded-button bg-warning/10 flex items-center justify-center">
                <BadgeDollarSign className="w-4 h-4 text-warning" />
              </div>
              <div>
                <h3 className="font-display text-display-sm text-text-primary">
                  Risk & Spend Limits
                </h3>
                <p className="text-body-sm text-text-muted mt-0.5">
                  Set caps agents must respect before taking action
                </p>
              </div>
            </div>

            <div className="space-y-4">
              <div>
                <label className="label-caps mb-2 block">Purchase Order Limit</label>
                <input
                  type="number"
                  min={0}
                  value={form.po_limit}
                  onChange={setNum("po_limit")}
                  className="w-full px-4 py-2.5 rounded-button bg-surface-2 border border-border text-text-primary font-mono text-body-sm focus:border-border-bright focus:outline-none transition-colors"
                />
                <p className="text-body-sm text-text-muted mt-1">
                  Maximum order value agents may approve autonomously
                </p>
              </div>

              <div>
                <label className="label-caps mb-2 block">Pricing Change Limit (%)</label>
                <input
                  type="number"
                  min={0}
                  max={100}
                  value={form.pricing_limit}
                  onChange={setNum("pricing_limit")}
                  className="w-full px-4 py-2.5 rounded-button bg-surface-2 border border-border text-text-primary font-mono text-body-sm focus:border-border-bright focus:outline-none transition-colors"
                />
                <p className="text-body-sm text-text-muted mt-1">
                  Maximum price change percentage agents may apply (0-100)
                </p>
              </div>

              <div>
                <label className="label-caps mb-2 block">Review Sentiment Threshold</label>
                <div className="flex items-center gap-3">
                  <input
                    type="range"
                    min={1}
                    max={5}
                    step={1}
                    value={form.reviews_rating_threshold}
                    onChange={(e) =>
                      setForm((p) => ({ ...p, reviews_rating_threshold: Number(e.target.value) }))
                    }
                    className="flex-1 accent-primary"
                  />
                  <div className="w-14 px-2 py-2 rounded-button bg-surface-2 border border-border text-center text-body-md text-text-primary font-mono">
                    {form.reviews_rating_threshold}
                  </div>
                </div>
                <p className="text-body-sm text-text-muted mt-1">
                  Minimum rating before negative-review agents may respond (1-5)
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Save / Errors */}
        <div className="card">
          {isError && (
            <div className="flex items-center gap-2 p-3 rounded-lg bg-danger-light border border-danger/20 mb-4">
              <AlertTriangle className="w-4 h-4 text-danger shrink-0" />
              <span className="text-sm text-danger">
                Failed to load settings. Showing last known values.
              </span>
            </div>
          )}

          {update.isError && (
            <div className="flex items-center gap-2 p-3 rounded-lg bg-danger-light border border-danger/20 mb-4">
              <AlertTriangle className="w-4 h-4 text-danger shrink-0" />
              <span className="text-sm text-danger">
                Failed to save settings. Try again.
              </span>
            </div>
          )}

          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-2 text-body-sm text-text-muted">
              <ShieldAlert className="w-4 h-4" />
              {isLoading
                ? "Loading current settings from the backend..."
                : !data
                  ? "Backend settings unavailable."
                  : "Values persist to the backend on save."}
            </div>
            <button
              onClick={handleSave}
              disabled={update.isPending || isLoading}
              className="btn-primary justify-center"
            >
              {update.isPending ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" /> Saving...
                </>
              ) : saved ? (
                <>
                  <CheckCircle className="w-4 h-4" /> Saved Successfully
                </>
              ) : (
                <>
                  <Save className="w-4 h-4" /> Save Changes
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </Shell>
  )
}