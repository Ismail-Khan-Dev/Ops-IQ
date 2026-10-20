import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  healthApi,
  approvalApi,
  agentApi,
  analyticsApi,
  settingsApi,
  securityApi,
  supportApi,
  cartRecoveryApi,
  shopifyApi,
  orderApi,
  productApi,
  reviewApi,
} from "./api"

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: healthApi.check,
    refetchInterval: 15_000,
    staleTime: 5_000,
    retry: 2,
  })
}

export function useApprovals(query?: { status?: string; agent?: string }) {
  return useQuery({
    queryKey: ["approvals", query],
    queryFn: () => approvalApi.list(query),
    refetchInterval: 30_000,
    staleTime: 10_000,
  })
}

export function useApproveAction() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id }: { id: string }) => approvalApi.approve(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["approvals"] })
      qc.invalidateQueries({ queryKey: ["analytics"] })
    },
  })
}

export function useRejectAction() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id }: { id: string }) => approvalApi.reject(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["approvals"] })
      qc.invalidateQueries({ queryKey: ["analytics"] })
    },
  })
}

export function useAgentStatus() {
  return useQuery({
    queryKey: ["agents"],
    queryFn: agentApi.status,
    refetchInterval: 30_000,
    staleTime: 10_000,
  })
}

export function useSetAgentAutonomy() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      agentId,
      level,
    }: {
      agentId: string
      level: "shadow" | "supervised" | "autonomous"
    }) => agentApi.setAutonomy(agentId, level),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agents"] })
      qc.invalidateQueries({ queryKey: ["analytics"] })
    },
  })
}

export function useAnalytics() {
  return useQuery({
    queryKey: ["analytics"],
    queryFn: () => analyticsApi.summary(),
    refetchInterval: 60_000,
    staleTime: 30_000,
  })
}

export function useSettings() {
  return useQuery({
    queryKey: ["settings"],
    queryFn: settingsApi.get,
    staleTime: 60_000,
  })
}

export function useUpdateSettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (patch: Parameters<typeof settingsApi.update>[0]) =>
      settingsApi.update(patch),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["settings"] })
    },
  })
}

export function useSecurityEvents(params?: { severity?: string }) {
  return useQuery({
    queryKey: ["security", "events", params],
    queryFn: () => securityApi.events(params),
    refetchInterval: 60_000,
    staleTime: 30_000,
  })
}

export function useSupportTickets(params?: { status?: string; priority?: string; page?: number; limit?: number }) {
  return useQuery({
    queryKey: ["support", "tickets", params],
    queryFn: () => supportApi.listTickets(params),
    refetchInterval: 30_000,
    staleTime: 10_000,
  })
}

export function useSupportTicket(id: string | null) {
  return useQuery({
    queryKey: ["support", "ticket", id],
    queryFn: () => supportApi.getTicket(id!),
    enabled: !!id,
    staleTime: 10_000,
  })
}

export function useSupportAnalytics(days = 7) {
  return useQuery({
    queryKey: ["support", "analytics", days],
    queryFn: () => supportApi.getAnalytics(days),
    staleTime: 60_000,
  })
}

export function useCartRecoveryAnalytics(days = 7) {
  return useQuery({
    queryKey: ["cart-recovery", "analytics", days],
    queryFn: cartRecoveryApi.analytics,
    staleTime: 60_000,
  })
}

export function useShopifyStatus() {
  return useQuery({
    queryKey: ["shopify", "status"],
    queryFn: shopifyApi.status,
    staleTime: 30_000,
  })
}

export function useShopifySync() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: shopifyApi.sync,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["shopify"] })
    },
  })
}

export function useOrders(params?: { page?: number; limit?: number; status?: string }) {
  return useQuery({
    queryKey: ["orders", params],
    queryFn: () => orderApi.list(params),
    staleTime: 10_000,
  })
}

export function useProducts(params?: { page?: number; limit?: number }) {
  return useQuery({
    queryKey: ["products", params],
    queryFn: () => productApi.list(params),
    staleTime: 10_000,
  })
}

export function useReviews(params?: { sentiment?: string }) {
  return useQuery({
    queryKey: ["reviews", params],
    queryFn: () => reviewApi.list(params),
    staleTime: 10_000,
  })
}

export function useCartItems(params?: { status?: string }) {
  return useQuery({
    queryKey: ["cart-items", params],
    queryFn: () => cartRecoveryApi.list(params),
    staleTime: 10_000,
  })
}
