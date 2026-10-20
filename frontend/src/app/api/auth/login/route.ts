import { NextRequest, NextResponse } from "next/server"
import {
  getBackendUrl,
  buildSessionCookieHeader,
  isSecureRequest,
} from "@/lib/server-helpers"

export const runtime = "nodejs"

/** POST /api/auth/login — validates API key against the backend, issues HttpOnly session cookie. */
export async function POST(request: NextRequest) {
  let apiKey: string
  try {
    const body = await request.json()
    apiKey = typeof body?.api_key === "string" ? body.api_key.trim() : ""
  } catch {
    return NextResponse.json({ detail: "Invalid request body" }, { status: 400 })
  }

  if (!apiKey) {
    return NextResponse.json({ detail: "API key is required" }, { status: 400 })
  }

  const backendUrl = getBackendUrl()
  let backendRes: Response
  try {
    backendRes = await fetch(`${backendUrl}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: apiKey }),
      cache: "no-store",
    })
  } catch {
    return NextResponse.json(
      { detail: "Backend is not reachable. Is the API server running?" },
      { status: 502 }
    )
  }

  const payload = await backendRes.json().catch(() => null)
  if (!backendRes.ok) {
    const status = backendRes.status === 401 ? 401 : backendRes.status
    return NextResponse.json(payload ?? { detail: "Login failed" }, { status })
  }

  const operator = payload?.operator || "api-operator"
  const secure = isSecureRequest(request)
  const setCookie = await buildSessionCookieHeader(apiKey, operator, secure)

  return NextResponse.json(
    { status: "ok", operator },
    { headers: { "Set-Cookie": setCookie } }
  )
}