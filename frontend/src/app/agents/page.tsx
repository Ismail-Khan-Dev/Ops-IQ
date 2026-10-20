"use client"

import { useMemo, useState } from "react"
import {
  Shield,
  ClipboardList,
  DollarSign,
  MessageSquare,
  Megaphone,
  ShoppingCart,
  Headphones,
  Bot,
  Loader2,
  TrendingUp,
  Gauge,
  RotateCcw,
  AlertTriangle,
} from "lucide-react"
import { toast } from "sonner"
import Shell from "@/components/layout/Shell"
import { Skeleton } from "@/components/shared/Skeleton"
import { ApiError, type AgentStatus } from "@/lib/api"
import { useAgentStatus, useSetAgentAutonomy } from "@/lib/hooks"

const GRADUATION_STREAK = 50

const AGENT_META: Record<
  string,
  { name: string; description: string; icon: typeof Bot }
> = {
  FraudAgent: {
    name: "Fraud Detection",
    description: "Real-time transaction auditing.",
    icon: Shield,
  },
  InventoryAgent: {
    name: "Inventory",
    description: "Stock optimization & replenishment.",
    icon: ClipboardList,
  },
  PricingAgent: {
    name: "Price Optimizer",
    description: "Dynamic market re-pricing.",
    icon: DollarSign,
  },
  ReviewsAgent: {
    name: "Review Moderator",
    description: "Sentiment & spam filtering.",
    icon: MessageSquare,
  },
  MarketingAgent: {
    name: "Marketing",
    description: "Ad spend and copy generation.",
    icon: Megaphone,
  },
  CartRecoveryAgent: {
    name: "Cart Recovery",
    description: "Drip campaigns & offer intent.",
    icon: ShoppingCart,
  },
  SupportAgent: {
    name: "Customer Support",
    description: "Tier-1 automated ticket resolution.",
    icon: Headphones,
  },
}

const AUTONOMY_CONFIG: Record<
  string,
  { label: string; badge: string; dot: string; bar: string }
> = {
  shadow: {
    label: "SHADOW",
    badge: "badge-muted",
    dot: "bg-text-muted",
    bar: "bg-primary",
  },
  supervised: {
    label: "SUPERVISED",
    badge: "badge-warning",
    dot: "bg-warning",
    bar: "bg-warning",
  },
  autonomous: {
    label: "AUTONOMOUS",
    badge: "badge-success",
    dot: "bg-success",
    bar: "bg-success",
  },
}

const AUTONOMY_LEVELS = ["shadow", "supervised", "autonomous"] as const

type AutonomyLevel = (typeof AUTONOMY_LEVELS)[number]

const FILTER_TABS = ["All Agents", "Shadow", "Supervised", "Autonomous"] as const

function isAutonomyLevel(value: string): value is AutonomyLevel {
  return (AUTONOMY_LEVELS as readonly string[]).includes(value)
}

function AgentCard({
  agent,
  isPending,
  onChangeLevel,
}: {
  agent: AgentStatus
  isPending: boolean
  onChangeLevel: (agent: AgentStatus, level: AutonomyLevel) => void
}) {
  const meta = AGENT_META[agent.agent_id] ?? {
    name: agent.agent_id,
    description: "Operational agent.",
    icon: Bot,
  }
  const Icon = meta.icon
  const level = isAutonomyLevel(agent.autonomy_level)
    ? agent.autonomy_level
    : "supervised"
  const config = AUTONOMY_CONFIG[level]
  const graduated = level === "autonomous"
  const progress = graduated
    ? 100
    : Math.min(Math.round((agent.streak / GRADUATION_STREAK) * 100), 100)
  const approvalRate =
    agent.total_decisions > 0
      ? Math.round((agent.total_approvals / agent.total_decisions) * 100)
      : 0

  const handleAction = () => {
    if (!graduated && level === "shadow") {
      onChangeLevel(agent, "supervised")
      return
    }
    let next: AutonomyLevel
    if (!graduated) {
      next = "autonomous"
    } else {
      next = "supervised"
    }
    onChangeLevel(agent, next)
  }

  const actionLabel = !graduated && level === "shadow"
    ? "Promote to Supervised"
    : graduated
      ? "Demote to Supervised"
      : "Graduate to Autonomous"

  return (
    <div className="card-hover group">
      <div className="flex items-start justify-between mb-3">
        <div className="w-10 h-10 rounded-button bg-primary/10 flex items-center justify-center">
          <Icon className="w-5 h-5 text-primary" />
        </div>
        <span className={config.badge}>
          <span className={`w-1.5 h-1.5 rounded-full ${config.dot}`} />
          {config.label}
        </span>
      </div>

      <h3 className="font-display font-semibold text-text-primary mb-1">
        {meta.name}
      </h3>
      <p className="text-body-sm text-text-muted mb-1">{meta.description}</p>
      <p className="font-mono text-[10px] text-text-muted mb-4">{agent.agent_id}</p>

      <div className="mb-4">
        <div className="flex items-center justify-between mb-1.5">
          <span className="label-caps text-[10px]">
            {graduated ? "Graduated" : "Graduation Streak"}
          </span>
          <span className="font-mono text-data-sm text-text-primary">
            {graduated ? `${agent.streak}+` : `${agent.streak} / ${GRADUATION_STREAK}`}
          </span>
        </div>
        <div className="progress-bar">
          <div
            className={`progress-fill ${config.bar}`}
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3 mb-4">
        <div>
          <div className="label-caps text-[10px] mb-0.5 flex items-center gap-1">
            <Gauge className="w-3 h-3" /> Confidence
          </div>
          <div className="font-mono text-data-sm text-text-primary">
            {Math.round(agent.avg_confidence * 100)}%
          </div>
        </div>
        <div>
          <div className="label-caps text-[10px] mb-0.5">Approvals</div>
          <div className="font-mono text-data-sm text-text-primary">
            {agent.total_approvals.toLocaleString()}
          </div>
        </div>
        <div>
          <div className="label-caps text-[10px] mb-0.5 flex items-center gap-1">
            <TrendingUp className="w-3 h-3" /> Rate
          </div>
          <div className="font-mono text-data-sm text-text-primary">{approvalRate}%</div>
        </div>
      </div>

      <button
        onClick={handleAction}
        disabled={isPending}
        className={
          graduated ? "btn-danger w-full justify-center" : "btn-primary w-full justify-center"
        }
      >
        {isPending ? (
          <>
            <Loader2 className="w-4 h-4 animate-spin" /> Updating...
          </>
        ) : graduated ? (
          <>
            <RotateCcw className="w-4 h-4" /> {actionLabel}
          </>
        ) : (
          <>
            <TrendingUp className="w-4 h-4" /> {actionLabel}
          </>
        )}
      </button>
    </div>
  )
}

export default function AgentsPage() {
  const { data, isLoading, isError, refetch } = useAgentStatus()
  const update = useSetAgentAutonomy()
  const [activeFilter, setActiveFilter] =
    useState<(typeof FILTER_TABS)[number]>("All Agents")

  const stats = useMemo(() => {
    const agents = data ?? []
    return {
      total: agents.length,
      autonomous: agents.filter((a) => a.autonomy_level === "autonomous").length,
      supervised: agents.filter((a) => a.autonomy_level === "supervised").length,
      shadow: agents.filter((a) => a.autonomy_level === "shadow").length,
    }
  }, [data])

  const filtered = useMemo(() => {
    const agents = data ?? []
    if (activeFilter === "All Agents") return agents
    return agents.filter((a) => a.autonomy_level === activeFilter.toLowerCase())
  }, [data, activeFilter])

  const handleChangeLevel = (agent: AgentStatus, level: AutonomyLevel) => {
    const meta = AGENT_META[agent.agent_id] ?? { name: agent.agent_id }
    if (level === "autonomous" || level === "supervised") {
      const intent =
        level === "autonomous"
          ? `Graduate ${meta.name} to autonomous?` +
            "\n\nIt will start executing actions without human approval."
          : `Demote ${meta.name} to supervised?\n\nIt will require human approval for every action.`
      if (!window.confirm(intent)) return
    }
    update.mutate(
      { agentId: agent.agent_id, level },
      {
        onSuccess: () => {
          toast.success(`${meta.name} is now ${level}`)
        },
        onError: (err: unknown) => {
          const message =
            err instanceof ApiError
              ? err.message
              : "Something went wrong while updating autonomy."
          toast.error(`Failed to update ${meta.name}: ${message}`)
        },
      },
    )
  }

  return (
    <Shell
      title="Autonomous Agents"
      subtitle="Graduate agents toward full autonomy as they earn your trust."
      actions={
        <div className="flex items-center gap-1 bg-surface rounded-card p-1 border border-border">
          {FILTER_TABS.map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveFilter(tab)}
              className={
                activeFilter === tab
                  ? "px-3 py-1.5 rounded-button text-xs font-medium bg-primary/15 text-primary transition-colors"
                  : "px-3 py-1.5 rounded-button text-xs font-medium text-text-muted hover:text-text-secondary transition-colors"
              }
            >
              {tab}
            </button>
          ))}
        </div>
      }
    >
      {isError && (
        <div className="flex items-center justify-between gap-4 p-4 rounded-lg bg-danger-light border border-danger/20 mb-6">
          <div className="flex items-center gap-2 text-body-sm text-danger">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            Failed to load agent status. Showing last known data.
          </div>
          <button onClick={() => refetch()} className="btn-outline">
            <RotateCcw className="w-4 h-4" /> Retry
          </button>
        </div>
      )}

      <div className="grid grid-cols-4 gap-4 mb-6">
        <div className="card">
          <div className="label-caps text-[10px] mb-1">Total Agents</div>
          <div className="font-mono text-display-sm text-text-primary">{stats.total}</div>
        </div>
        <div className="card">
          <div className="label-caps text-[10px] mb-1">Autonomous</div>
          <div className="font-mono text-display-sm text-success">{stats.autonomous}</div>
        </div>
        <div className="card">
          <div className="label-caps text-[10px] mb-1">Supervised</div>
          <div className="font-mono text-display-sm text-warning">{stats.supervised}</div>
        </div>
        <div className="card">
          <div className="label-caps text-[10px] mb-1">Shadow</div>
          <div className="font-mono text-display-sm text-text-primary">{stats.shadow}</div>
        </div>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="card">
              <Skeleton className="w-10 h-10 rounded-lg mb-4" />
              <Skeleton className="h-4 w-2/3 mb-2" />
              <Skeleton className="h-3 w-1/2 mb-4" />
              <Skeleton className="h-2 w-full mb-1" />
              <Skeleton className="h-2 w-3/4 mb-4" />
              <Skeleton className="h-9 w-full" />
            </div>
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="card flex flex-col items-center justify-center gap-3 py-16 text-center">
          <Bot className="w-8 h-8 text-text-muted" />
          <p className="text-body-md text-text-muted">
            {activeFilter === "All Agents"
              ? "No agents have emitted decisions yet. Run a pipeline to create agent status rows."
              : `No agents are currently in "${activeFilter}" autonomy.`}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-4 gap-4">
          {filtered.map((agent) => (
            <AgentCard
              key={agent.agent_id}
              agent={agent}
              isPending={update.isPending && update.variables?.agentId === agent.agent_id}
              onChangeLevel={handleChangeLevel}
            />
          ))}
        </div>
      )}
    </Shell>
  )
}