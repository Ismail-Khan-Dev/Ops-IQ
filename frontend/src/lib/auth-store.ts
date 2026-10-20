import { create } from "zustand"
import { persist } from "zustand/middleware"
import { authApi, ApiError } from "./api"

interface AuthState {
  operator: string | null
  isAuthenticated: boolean
  isLoading: boolean
  error: string | null

  login: (apiKey: string) => Promise<boolean>
  logout: () => Promise<void>
  checkSession: () => Promise<boolean>
  clearError: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      operator: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,

      login: async (apiKey: string) => {
        set({ isLoading: true, error: null })
        try {
          const res = await authApi.login(apiKey)
          if (res.status === "ok") {
            set({
              operator: res.operator ?? "api-operator",
              isAuthenticated: true,
              isLoading: false,
              error: null,
            })
            return true
          }
          set({ isLoading: false, error: "Login failed" })
          return false
        } catch (err) {
          const message =
            err instanceof ApiError
              ? err.status === 401
                ? "Invalid API key"
                : err.status === 502
                  ? "Connection failed — is the backend running?"
                  : `Server error (${err.status})`
              : "Connection failed — is the backend running?"
          set({ isLoading: false, error: message })
          return false
        }
      },

      logout: async () => {
        try {
          await authApi.logout()
        } catch {
          // Best-effort: continue clearing local state even if backend is down.
        }
        set({
          operator: null,
          isAuthenticated: false,
          error: null,
        })
      },

      checkSession: async () => {
        try {
          const res = await authApi.me()
          if (res.authenticated) {
            set({
              operator: res.operator ?? "api-operator",
              isAuthenticated: true,
              error: null,
            })
            return true
          }
        } catch {
          // no session or backend down
        }
        set({ isAuthenticated: false, operator: null })
        return false
      },

      clearError: () => set({ error: null }),
    }),
    {
      name: "opsiq-auth",
      // Only persist the operator string. The API key and real session live
      // server-side in an HttpOnly cookie and are never exposed to JS.
      partialize: (state) => ({
        operator: state.operator,
      }),
    },
  ),
)