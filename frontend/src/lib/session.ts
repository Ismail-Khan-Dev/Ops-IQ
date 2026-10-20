/**
 * Server-side session management for the BFF.
 *
 * Sessions are stateless, signed cookies (payload.signature, HMAC-SHA256).
 * Only the Next.js server can issue/verify a session — the browser only ever
 * holds the opaque HttpOnly cookie. The raw API key is never exposed to JS.
 *
 * Works in both the Edge runtime (middleware) and Node (route handlers) via
 * the Web Crypto API. No Buffer / node-specific globals are used.
 */

const SESSION_COOKIE_NAME = "opsiq_session"
const SESSION_TTL_MS = 24 * 60 * 60 * 1000 // 24 hours

interface SessionPayload {
  apiKey: string
  operator: string
  exp: number // epoch ms
}

let devSecret: string | undefined

function generateRandomSecret(): string {
  const bytes = new Uint8Array(32)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("")
}

function getSecret(): string {
  const secret = process.env.SESSION_SECRET
  if (secret) return secret
  if (process.env.NODE_ENV === "production") {
    throw new Error(
      "SESSION_SECRET is not set. Generate one with `openssl rand -hex 32` and set it as an environment variable before starting the frontend in production."
    )
  }
  // Non-production only: a random per-process key so sessions cannot be forged
  // with a publicly-known constant. Production MUST set SESSION_SECRET.
  if (!devSecret) devSecret = generateRandomSecret()
  return devSecret
}

// ── Base64url helpers (no Buffer) ─────────────────────────────
function bytesToB64url(bytes: Uint8Array): string {
  let binary = ""
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i])
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "")
}

function b64urlToBytes(input: string): Uint8Array<ArrayBuffer> {
  const b64 = input.replace(/-/g, "+").replace(/_/g, "/")
  const padded = b64 + "=".repeat((4 - (b64.length % 4)) % 4)
  const binary = atob(padded)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
  return bytes
}

const encoder = new TextEncoder()

function stringToB64url(input: string): string {
  return bytesToB64url(encoder.encode(input))
}

function b64urlToString(input: string): string {
  return new TextDecoder().decode(b64urlToBytes(input))
}

async function sign(message: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(getSecret()),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"]
  )
  const sig = await crypto.subtle.sign("HMAC", key, encoder.encode(message))
  return bytesToB64url(new Uint8Array(sig))
}

async function verifySignature(message: string, signatureB64: string): Promise<boolean> {
  try {
    const key = await crypto.subtle.importKey(
      "raw",
      encoder.encode(getSecret()),
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["sign", "verify"]
    )
    return await crypto.subtle.verify(
      "HMAC",
      key,
      b64urlToBytes(signatureB64),
      encoder.encode(message)
    )
  } catch {
    return false
  }
}

export async function createSessionCookieValue(
  apiKey: string,
  operator: string
): Promise<string> {
  const payload: SessionPayload = {
    apiKey,
    operator,
    exp: Date.now() + SESSION_TTL_MS,
  }
  const encoded = stringToB64url(JSON.stringify(payload))
  const sig = await sign(encoded)
  return `${encoded}.${sig}`
}

export async function parseSessionCookieValue(
  value: string | undefined | null
): Promise<SessionPayload | null> {
  if (!value) return null
  const dot = value.indexOf(".")
  if (dot <= 0) return null
  const encoded = value.slice(0, dot)
  const sig = value.slice(dot + 1)
  const valid = await verifySignature(encoded, sig)
  if (!valid) return null
  try {
    const payload = JSON.parse(b64urlToString(encoded)) as SessionPayload
    if (!payload.apiKey || !payload.exp || payload.exp < Date.now()) return null
    return payload
  } catch {
    return null
  }
}

export { SESSION_COOKIE_NAME, SESSION_TTL_MS }