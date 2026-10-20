"use client"

import { useCallback, useEffect, useRef, useState } from "react"

const WS_BASE_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/ws/queue"
const RECONNECT_BASE_MS = 1_000
const RECONNECT_MAX_MS = 30_000
const PING_INTERVAL_MS = 30_000
const TICKET_TTL_MARGIN_MS = 5_000

// WebSocket close codes matching backend
const CLOSE_AUTH_FAILED = 4001
const CLOSE_RATE_LIMITED = 4008
const CLOSE_TOO_MANY = 4013

export type WSEvent =
  | { type: "action_updated"; payload: Record<string, unknown> }
  | { type: "pipeline_started"; payload: Record<string, unknown> }
  | { type: "pipeline_completed"; payload: Record<string, unknown> }
  | { type: "pipeline_failed"; payload: Record<string, unknown> }
  | { type: "agent_status"; payload: Record<string, unknown> }
  | { type: "notification"; payload: Record<string, unknown> }
  | { type: "error"; payload: { code: string } }
  | { type: "pong" }
  | { type: string; payload?: Record<string, unknown> }

interface UseWebSocketOptions {
  onEvent?: (event: WSEvent) => void
  onConnect?: () => void
  onDisconnect?: () => void
  enabled?: boolean
}

interface WebSocketState {
  isConnected: boolean
  isConnecting: boolean
  reconnectAttempt: number
  lastEvent: WSEvent | null
  authFailed: boolean
}

/**
 * Fetch a short-lived, single-use WS ticket from the BFF. The ticket is issued
 * server-side from the HttpOnly session; the raw API key never touches JS.
 */
async function fetchTicket(): Promise<{ ticket: string; ttlMs: number }> {
  const res = await fetch("/api/auth/ws-ticket", { cache: "no-store" })
  if (!res.ok) {
    throw new Error(`ws-ticket failed: ${res.status}`)
  }
  const body = await res.json().catch(() => null)
  if (!body?.ticket) {
    throw new Error("ws-ticket returned no ticket")
  }
  const ttlSeconds = Number(body.ttl_seconds || 60)
  return { ticket: body.ticket as string, ttlMs: ttlSeconds * 1000 }
}

export function useWebSocket(options: UseWebSocketOptions = {}) {
  const { onEvent, onConnect, onDisconnect, enabled = true } = options
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pingTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  const attemptRef = useRef(0)
  const authFailedRef = useRef(false)
  const ticketExpiryRef = useRef(0)

  // Use refs for all callbacks to avoid stale closures and circular deps
  const onEventRef = useRef(onEvent)
  const onConnectRef = useRef(onConnect)
  const onDisconnectRef = useRef(onDisconnect)
  const enabledRef = useRef(enabled)
  const connectRef = useRef<() => Promise<void>>()

  onEventRef.current = onEvent
  onConnectRef.current = onConnect
  onDisconnectRef.current = onDisconnect
  enabledRef.current = enabled

  const [state, setState] = useState<WebSocketState>({
    isConnected: false,
    isConnecting: false,
    reconnectAttempt: 0,
    lastEvent: null,
    authFailed: false,
  })

  const cleanup = useCallback(() => {
    if (pingTimer.current) {
      clearInterval(pingTimer.current)
      pingTimer.current = null
    }
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current)
      reconnectTimer.current = null
    }
  }, [])

  const scheduleReconnect = useCallback(() => {
    if (!enabledRef.current || authFailedRef.current) return
    const delay = Math.min(
      RECONNECT_BASE_MS * Math.pow(2, attemptRef.current),
      RECONNECT_MAX_MS,
    )
    attemptRef.current += 1
    setState((s) => ({ ...s, reconnectAttempt: attemptRef.current }))

    reconnectTimer.current = setTimeout(() => {
      connectRef.current?.()
    }, delay)
  }, [])

  const connect = useCallback(async () => {
    if (!enabledRef.current) return
    if (wsRef.current?.readyState === WebSocket.OPEN) return
    if (authFailedRef.current) return

    setState((s) => ({ ...s, isConnecting: true }))

    try {
      // Mint a fresh single-use ticket from the BFF per connection attempt.
      const { ticket, ttlMs } = await fetchTicket()
      ticketExpiryRef.current = Date.now() + ttlMs - TICKET_TTL_MARGIN_MS

      const base = WS_BASE_URL
      const finalUrl = `${base}${base.includes("?") ? "&" : "?"}ticket=${encodeURIComponent(ticket)}`
      const ws = new WebSocket(finalUrl)

      ws.onopen = () => {
        attemptRef.current = 0
        authFailedRef.current = false
        setState((s) => ({
          ...s,
          isConnected: true,
          isConnecting: false,
          reconnectAttempt: 0,
          authFailed: false,
        }))
        onConnectRef.current?.()

        pingTimer.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "ping" }))
          }
        }, PING_INTERVAL_MS)
      }

      ws.onmessage = (msg) => {
        try {
          const event: WSEvent = JSON.parse(msg.data)
          if (event.type === "pong") return

          if (event.type === "error" && event.payload?.code === "rate_limited") {
            return
          }

          setState((s) => ({ ...s, lastEvent: event }))
          onEventRef.current?.(event)
        } catch {
          // Ignore malformed messages
        }
      }

      ws.onclose = (event) => {
        cleanup()

        // Auth failed — don't reconnect
        if (
          event.code === CLOSE_AUTH_FAILED ||
          event.code === CLOSE_TOO_MANY ||
          event.code === CLOSE_RATE_LIMITED
        ) {
          authFailedRef.current = true
          setState((s) => ({
            ...s,
            isConnected: false,
            isConnecting: false,
            authFailed: true,
          }))
          return
        }

        setState((s) => ({ ...s, isConnected: false, isConnecting: false }))
        onDisconnectRef.current?.()
        scheduleReconnect()
      }

      ws.onerror = () => {
        ws.close()
      }

      wsRef.current = ws
    } catch {
      setState((s) => ({ ...s, isConnecting: false }))
      scheduleReconnect()
    }
  }, [cleanup, scheduleReconnect])

  // Update connectRef after connect is defined
  connectRef.current = connect

  const disconnect = useCallback(() => {
    cleanup()
    wsRef.current?.close()
    wsRef.current = null
    setState({
      isConnected: false,
      isConnecting: false,
      reconnectAttempt: 0,
      lastEvent: null,
      authFailed: false,
    })
    authFailedRef.current = false
    ticketExpiryRef.current = 0
  }, [cleanup])

  // Reset auth state after a new session is established (e.g., after login)
  const resetAuth = useCallback(() => {
    authFailedRef.current = false
    ticketExpiryRef.current = 0
    setState((s) => ({ ...s, authFailed: false }))
    attemptRef.current = 0
    connect()
  }, [connect])

  useEffect(() => {
    connect()
    return () => {
      cleanup()
      wsRef.current?.close()
    }
  }, [connect, cleanup])

  return {
    ...state,
    disconnect,
    reconnect: () => connect(),
    resetAuth,
  }
}