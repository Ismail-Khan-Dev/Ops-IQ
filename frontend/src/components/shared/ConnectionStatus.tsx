"use client"

import { useWs } from "@/app/providers"
import { Wifi, WifiOff, Loader2, ShieldAlert } from "lucide-react"
import { cn } from "@/lib/utils"

export function ConnectionStatus() {
  const { isConnected, isConnecting, authFailed } = useWs()

  return (
    <div
      className={cn(
        "flex items-center gap-1.5 px-2 py-1 rounded-md text-[11px] font-mono transition-colors",
        authFailed
          ? "bg-warning/10 text-warning"
          : isConnected
            ? "bg-success/10 text-success"
            : isConnecting
              ? "bg-warning/10 text-warning"
              : "bg-danger/10 text-danger",
      )}
    >
      {authFailed ? (
        <ShieldAlert className="w-3 h-3" />
      ) : isConnected ? (
        <Wifi className="w-3 h-3" />
      ) : isConnecting ? (
        <Loader2 className="w-3 h-3 animate-spin" />
      ) : (
        <WifiOff className="w-3 h-3" />
      )}
      {authFailed
        ? "Auth Required"
        : isConnected
          ? "Live"
          : isConnecting
            ? "Connecting..."
            : "Offline"}
    </div>
  )
}
