"use client"

import { usePathname, useRouter } from "next/navigation"
import { useEffect, useRef } from "react"
import { useAuthStore } from "@/lib/auth-store"

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, checkSession } = useAuthStore()
  const router = useRouter()
  const pathname = usePathname()
  const checkedRef = useRef(false)

  // On first mount (e.g., a hard refresh), verify the HttpOnly session against
  // the BFF so a stale Zustand persist value can't grant access.
  useEffect(() => {
    if (checkedRef.current) return
    checkedRef.current = true
    checkSession().then((valid) => {
      if (!valid && pathname !== "/login") {
        router.replace("/login")
      }
    })
  }, [checkSession, pathname, router])

  useEffect(() => {
    if (!isAuthenticated && pathname !== "/login") {
      router.replace("/login")
    }
  }, [isAuthenticated, pathname, router])

  // Gate: render children only when authenticated or on the login page itself.
  if (!isAuthenticated && pathname !== "/login") {
    return null
  }

  return <>{children}</>
}