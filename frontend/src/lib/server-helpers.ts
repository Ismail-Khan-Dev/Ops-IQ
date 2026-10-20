import { NextResponse } from "next/server"
import {
  SESSION_COOKIE_NAME,
  SESSION_TTL_MS,
  createSessionCookieValue,
  parseSessionCookieValue,
} from "@/lib/session"

/**
 * Server-side helpers shared by the BFF route handlers (Node runtime).
 */

export function getBackendUrl(): string {
  const url = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
  return url.replace(/\/+$/, "")
}

export function isSecureRequest(request: Request): boolean {
  return request.headers.get("x-forwarded-proto") === "https"
}

/** Expire the session cookie on the client. */
export function clearSessionCookie(): Response {
  return NextResponse.json(
    { status: "ok" },
    {
      headers: {
        "Set-Cookie": `${SESSION_COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0`,
      },
    }
  )
}

/** Read and verify the session from a request; returns the session or null. */
export async function readSessionFromRequest(
  request: Request
): Promise<{ apiKey: string; operator: string } | null> {
  const cookie = request.headers.get("cookie") || ""
  const match = cookie.match(new RegExp(`(?:^|;\\s*)${SESSION_COOKIE_NAME}=([^;]*)`))
  if (!match) return null
  const session = await parseSessionCookieValue(decodeURIComponent(match[1]))
  if (!session) return null
  return { apiKey: session.apiKey, operator: session.operator }
}

/** Build a Set-Cookie header that issues a fresh signed session cookie. */
export async function buildSessionCookieHeader(
  apiKey: string,
  operator: string,
  secure: boolean
): Promise<string> {
  const value = await createSessionCookieValue(apiKey, operator)
  const secureFlag = secure ? "; Secure" : ""
  const expires = new Date(Date.now() + SESSION_TTL_MS).toUTCString()
  return `${SESSION_COOKIE_NAME}=${encodeURIComponent(value)}; Path=/; HttpOnly; SameSite=Strict; Expires=${expires}${secureFlag}`
}