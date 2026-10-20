import { NextRequest, NextResponse } from "next/server"
import { getBackendUrl, readSessionFromRequest } from "@/lib/server-helpers"

export const runtime = "nodejs"

/**
 * GET /api/auth/ws-ticket
 *
 * Exchanges the server-side session (HttpOnly cookie) for a short-lived,
 * single-use WebSocket ticket issued by the backend. The raw API key is never
 * placed in the WS query string — only this short-lived ticket is.
 */
export async function GET(request: NextRequest) {
  const session = await readSessionFromRequest(request)
  if (!session) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 })
  }

  const backendUrl = getBackendUrl()
  let backendRes: Response
  try {
    backendRes = await fetch(`${backendUrl}/api/auth/ws-ticket`, {
      method: "GET",
      headers: { Authorization: `Bearer ${session.apiKey}` },
      cache: "no-store",
    })
  } catch {
    return NextResponse.json(
      { detail: "Backend is not reachable. Cannot issue WS ticket." },
      { status: 502 }
    )
  }

  const payload = await backendRes.json().catch(() => null)
  if (!backendRes.ok) {
    return NextResponse.json(
      payload ?? { detail: "Failed to issue WebSocket ticket" },
      { status: backendRes.status }
    )
  }

  return NextResponse.json(payload)
}