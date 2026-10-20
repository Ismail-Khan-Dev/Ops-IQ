import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'
import { SESSION_COOKIE_NAME, parseSessionCookieValue } from '@/lib/session'

const publicRoutes = ['/login', '/api/auth/login']

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl

  if (publicRoutes.some((r) => pathname.startsWith(r))) {
    return NextResponse.next()
  }

  // API routes are authorized inside the route handlers (they return JSON 401).
  // Only gate page routes here.
  const isApi = pathname.startsWith('/api/')
  const cookie = request.cookies.get(SESSION_COOKIE_NAME)?.value

  let validSession = false
  if (cookie) {
    try {
      const session = await parseSessionCookieValue(cookie)
      validSession = !!session
    } catch {
      validSession = false
    }
  }

  const response = NextResponse.next()
  response.headers.set('x-pathname', pathname)

  if (validSession) {
    return response
  }

  // Signed HttpOnly session present but expired/invalid and client asked via XHR.
  if (isApi) {
    response.headers.set('x-requires-auth', 'true')
    return response
  }

  const loginUrl = new URL('/login', request.url)
  loginUrl.searchParams.set('redirect', pathname)
  return NextResponse.redirect(loginUrl)
}

export const config = {
  matcher: [
    '/((?!_next/static|_next/image|favicon.ico|public/).*)',
  ],
}