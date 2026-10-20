import { describe, it, expect } from 'vitest'
import {
  readTraceparent,
  newTraceparent,
  applyTraceContext,
} from '@/lib/trace-context'

const TRACEPARENT_RE = /^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$/

describe('trace context', () => {
  it('generates a well-formed W3C traceparent', () => {
    const tp = newTraceparent()
    expect(tp).toMatch(TRACEPARENT_RE)
    expect(tp.endsWith('-01')).toBe(true)
  })

  it('generates unique trace contexts', () => {
    const a = newTraceparent()
    const b = newTraceparent()
    expect(a).not.toBe(b)
  })

  it('reads a valid traceparent from headers', () => {
    const headers = new Headers({
      traceparent: '00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01',
    })
    expect(readTraceparent(headers)).toBe('00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01')
  })

  it('rejects malformed traceparent headers', () => {
    const headers = new Headers({ traceparent: 'not-a-traceparent' })
    expect(readTraceparent(headers)).toBeUndefined()
  })

  it('inherits an upstream traceparent when present', () => {
    const upstream = '00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01'
    const headers = new Headers({ traceparent: upstream, tracestate: 'vendor=abc' })
    applyTraceContext(headers)
    expect(headers.get('traceparent')).toBe(upstream)
    expect(headers.get('tracestate')).toBe('vendor=abc')
  })

  it('sets a generated traceparent when none is present', () => {
    const headers = new Headers()
    applyTraceContext(headers)
    const tp = headers.get('traceparent')
    expect(tp).toMatch(TRACEPARENT_RE)
    expect(headers.get('tracestate')).toBeNull()
  })
})