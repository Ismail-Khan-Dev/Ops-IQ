"use client"
import Sidebar, { useSidebar } from "./Sidebar"
import Topbar from "./Topbar"

export default function Shell({ children, title, subtitle, actions }: {
  children: React.ReactNode
  title?: string
  subtitle?: string
  actions?: React.ReactNode
}) {
  const sidebar = useSidebar()

  return (
    <div className="min-h-screen bg-void">
      <Sidebar open={sidebar.open} onClose={sidebar.close} />
      <div className="lg:ml-[240px]">
        <Topbar
          title={title}
          subtitle={subtitle}
          actions={actions}
          onMenuToggle={sidebar.toggle}
        />
        <main id="main-content" className="p-4 sm:p-6" role="main">
          {children}
        </main>
      </div>
    </div>
  )
}
