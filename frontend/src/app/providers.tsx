"use client"

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { createContext, useCallback, useContext, useMemo, useState } from "react"
import { Toaster } from "sonner"
import { useWebSocket, type WSEvent } from "@/lib/useWebSocket"
import { useAuthStore } from "@/lib/auth-store"

interface WsContextValue {
  isConnected: boolean
  isConnecting: boolean
  reconnectAttempt: number
  lastEvent: WSEvent | null
  authFailed: boolean
  reconnect: () => void
  resetAuth: () => void
}

const WsContext = createContext<WsContextValue>({
  isConnected: false,
  isConnecting: false,
  reconnectAttempt: 0,
  lastEvent: null,
  authFailed: false,
  reconnect: () => {},
  resetAuth: () => {},
})

export function useWs() {
  return useContext(WsContext)
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 10_000,
            refetchInterval: 30_000,
            retry: 2,
            refetchOnWindowFocus: true,
          },
        },
      }),
  )

  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)

  const onEvent = useCallback((event: WSEvent) => {
    if (event.type === "action_updated" || event.type === "pipeline_completed") {
      queryClient.invalidateQueries({ queryKey: ["approvals"] })
      queryClient.invalidateQueries({ queryKey: ["analytics"] })
    }
    if (event.type === "agent_status") {
      queryClient.invalidateQueries({ queryKey: ["agents"] })
    }
  }, [queryClient])

  const ws = useWebSocket({ onEvent, enabled: isAuthenticated })

  const wsValue = useMemo(
    () => ({
      isConnected: ws.isConnected,
      isConnecting: ws.isConnecting,
      reconnectAttempt: ws.reconnectAttempt,
      lastEvent: ws.lastEvent,
      authFailed: ws.authFailed,
      reconnect: ws.reconnect,
      resetAuth: ws.resetAuth,
    }),
    [ws.isConnected, ws.isConnecting, ws.reconnectAttempt, ws.lastEvent, ws.authFailed, ws.reconnect, ws.resetAuth],
  )

  return (
    <QueryClientProvider client={queryClient}>
      <WsContext.Provider value={wsValue}>
        {children}
        <Toaster
          position="bottom-right"
          toastOptions={{
            style: {
              background: '#111827',
              border: '1px solid rgba(99, 102, 241, 0.10)',
              color: '#F1F5F9',
              fontSize: '14px',
            },
          }}
          theme="dark"
        />
      </WsContext.Provider>
    </QueryClientProvider>
  )
}
