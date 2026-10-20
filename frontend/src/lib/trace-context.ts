import { randomUUID } from "crypto"

/**
 * Minimal W3C Trace Context support for the BFF proxy.
 *
 * The backend instruments outgoing requests with OpenTelemetry and recognizes
 * standard `traceparent` / `tracestate` headers. Because browsers generally do
 * not emit them, we generate a valid `traceparent` on the server for every
 * proxied request (inheriting one when the caller already provides it) so the
 * backend can correlate the full request chain end-to-end in Tempo.
 *
 * Format (W3C): `version-trace-id-parent-id-flags`
 *   trace-id : 32 hex chars
 *   parent-id: 16 hex chars
 *   flags    : 01 = recorded/sampled
 */

const TRACEPARENT_RE = /^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$/

function randomHex(length: number): string {
  return randomUUID().replace(/-/g, "").slice(0, length)
}

/** Return the request's traceparent if it is well-formed, else undefined. */
export function readTraceparent(headers: Headers): string | undefined {
  const value = headers.get("traceparent")
  if (value && TRACEPARENT_RE.test(value.trim())) {
    return value.trim()
  }
  return undefined
}

/** Generate a fresh, root W3C traceparent (sampled). */
export function newTraceparent(): string {
  return `00-${randomHex(32)}-${randomHex(16)}-01`
}

/**
 * Apply W3C trace context to the outgoing backend headers.
 * Inherits a caller-provided traceparent when present, otherwise generates
 * one. `tracestate` is only forwarded when the traceparent is inherited.
 */
export function applyTraceContext(headers: Headers): void {
  const parent = readTraceparent(headers)
  if (parent) {
    headers.set("traceparent", parent)
    return
  }
  headers.set("traceparent", newTraceparent())
  // No valid upstream trace context: drop any stale tracestate so we never
  // emit a mismatched pair.
  headers.delete("tracestate")
}