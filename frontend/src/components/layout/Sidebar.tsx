"use client"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { useState, useEffect } from "react"
import {
  LayoutDashboard, Bot, ShoppingCart, Headphones, Package,
  Star, BarChart3, Store, Shield, Settings, Zap, Plus, X
} from "lucide-react"

const navSections = [
  {
    label: null,
    items: [
      { href: "/", label: "Dashboard", icon: LayoutDashboard },
      { href: "/agents", label: "Agents", icon: Bot },
    ],
  },
  {
    label: null,
    items: [
      { href: "/orders", label: "Orders", icon: ShoppingCart },
      { href: "/cart-recovery", label: "Cart Recovery", icon: Package },
      { href: "/support", label: "Support", icon: Headphones },
    ],
  },
  {
    label: null,
    items: [
      { href: "/products", label: "Products", icon: Package },
      { href: "/reviews", label: "Reviews", icon: Star },
    ],
  },
  {
    label: null,
    items: [
      { href: "/analytics", label: "Analytics", icon: BarChart3 },
      { href: "/shopify", label: "Shopify", icon: Store },
    ],
  },
  {
    label: "SYSTEM",
    items: [
      { href: "/security", label: "Security", icon: Shield },
      { href: "/settings", label: "Settings", icon: Settings },
    ],
  },
]

interface SidebarProps {
  open: boolean
  onClose: () => void
}

function SidebarContent({ onClose }: { onClose?: () => void }) {
  const pathname = usePathname()

  useEffect(() => {
    onClose?.()
  }, [pathname, onClose])

  return (
    <aside className="fixed left-0 top-0 bottom-0 w-[240px] bg-surface border-r border-border flex flex-col z-50" aria-label="Main navigation">
      <div className="p-5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-primary flex items-center justify-center shadow-sm" aria-hidden="true">
            <Zap className="w-5 h-5 text-white" />
          </div>
          <div>
            <div className="font-display font-bold text-[15px] text-text-primary leading-tight">OpsIQ</div>
            <div className="text-[10px] font-mono uppercase tracking-widest text-text-muted">AI Automation</div>
          </div>
        </div>
        <button onClick={onClose} className="lg:hidden w-8 h-8 rounded-button flex items-center justify-center text-text-muted hover:bg-surface-3" aria-label="Close menu">
          <X className="w-4 h-4" />
        </button>
      </div>

      <nav className="flex-1 px-3 space-y-0.5 overflow-y-auto" aria-label="Navigation">
        {navSections.map((section, si) => (
          <div key={si}>
            {section.label && (
              <div className="label-caps px-3 pt-5 pb-2">{section.label}</div>
            )}
            {section.items.map((item) => {
              const active = pathname === item.href
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={active ? "sidebar-link-active" : "sidebar-link"}
                  aria-current={active ? "page" : undefined}
                >
                  <item.icon className="w-4 h-4 shrink-0" />
                  <span>{item.label}</span>
                </Link>
              )
            })}
          </div>
        ))}
      </nav>

      <div className="p-3 border-t border-border">
        <Link href="/agents" className="btn-primary w-full text-sm">
          <Plus className="w-4 h-4" />
          Deploy Agent
        </Link>
      </div>

      <div className="px-5 py-3 border-t border-border">
        <div className="flex items-center gap-2 text-xs">
          <div className="dot-green" />
          <span className="text-text-secondary">System Healthy</span>
          <span className="ml-auto font-mono text-success font-medium">94%</span>
        </div>
        <div className="progress-bar mt-2">
          <div className="progress-fill bg-success" style={{ width: "94%" }} />
        </div>
      </div>
    </aside>
  )
}

export default function Sidebar({ open, onClose }: SidebarProps) {
  return (
    <>
      <div className="hidden lg:block">
        <SidebarContent />
      </div>

      {open && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-black/20 backdrop-blur-sm" onClick={onClose} />
          <SidebarContent onClose={onClose} />
        </div>
      )}
    </>
  )
}

export function useSidebar() {
  const [open, setOpen] = useState(false)
  return { open, setOpen, toggle: () => setOpen((o) => !o), close: () => setOpen(false) }
}
