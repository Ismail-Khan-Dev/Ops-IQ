import { NextRequest, NextResponse } from "next/server"
import { clearSessionCookie } from "@/lib/server-helpers"

export const runtime = "nodejs"

/** POST /api/auth/logout — clears the HttpOnly session cookie. */
export async function POST(_request: NextRequest) {
  return clearSessionCookie()
}