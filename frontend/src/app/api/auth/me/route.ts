import { NextRequest, NextResponse } from "next/server"
import { readSessionFromRequest } from "@/lib/server-helpers"

export const runtime = "nodejs"

/** GET /api/auth/me — returns the authenticated operator or 401. */
export async function GET(request: NextRequest) {
  const session = await readSessionFromRequest(request)
  if (!session) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 })
  }
  return NextResponse.json({
    status: "ok",
    operator: session.operator,
    authenticated: true,
  })
}