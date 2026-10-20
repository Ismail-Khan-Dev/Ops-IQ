import type { Metadata } from "next"
import { Inter, Space_Grotesk, JetBrains_Mono } from "next/font/google"
import dynamic from "next/dynamic"
import "../styles/globals.css"
import { Providers } from "./providers"
import { CommandPaletteProvider } from "@/components/CommandPalette"
import { ErrorBoundary } from "@/components/shared/ErrorBoundary"
import { AuthGuard } from "@/components/auth/AuthGuard"

const CommandPalette = dynamic(
  () => import("@/components/CommandPalette").then((m) => m.default),
  {
    ssr: false,
    loading: () => null,
  }
)

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
})

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-space-grotesk",
})

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
})

export const metadata: Metadata = {
  title: {
    default: "OpsIQ — AI-Powered E-Commerce Operations",
    template: "%s | OpsIQ",
  },
  description: "Intelligent automation for fraud detection, inventory, pricing, and customer support",
  keywords: ["ecommerce", "automation", "AI", "fraud detection", "inventory", "pricing", "customer support"],
  authors: [{ name: "Ismail-2001" }],
  creator: "OpsIQ",
  openGraph: {
    type: "website",
    locale: "en_US",
    url: "https://ops-iq.dev",
    title: "OpsIQ — AI-Powered E-Commerce Operations",
    description: "Intelligent automation for fraud detection, inventory, pricing, and customer support",
    siteName: "OpsIQ",
  },
  twitter: {
    card: "summary_large_image",
    title: "OpsIQ — AI-Powered E-Commerce Operations",
    description: "Intelligent automation for fraud detection, inventory, pricing, and customer support",
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-video-preview": -1,
      "max-image-preview": "large",
      "max-snippet": -1,
    },
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className="dark">
      <body
        className={`${inter.variable} ${spaceGrotesk.variable} ${jetbrainsMono.variable} font-body antialiased`}
      >
        <Providers>
          <CommandPaletteProvider>
            <a
              href="#main-content"
              className="sr-only focus:not-sr-only focus:absolute focus:z-[100] focus:top-4 focus:left-4 focus:bg-primary focus:text-white focus:px-4 focus:py-2 focus:rounded-lg"
            >
              Skip to main content
            </a>
            <CommandPalette />
            <ErrorBoundary>
              <AuthGuard>{children}</AuthGuard>
            </ErrorBoundary>
          </CommandPaletteProvider>
        </Providers>
      </body>
    </html>
  )
}
