/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ["class"],
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        bg: {
          DEFAULT: "#FFFFFF",
          secondary: "#F8FAFC",
          tertiary: "#F1F5F9",
        },
        surface: {
          DEFAULT: "#FFFFFF",
          2: "#F8FAFC",
          3: "#F1F5F9",
          4: "#E2E8F0",
        },
        border: {
          DEFAULT: "#E2E8F0",
          light: "#F1F5F9",
          dark: "#CBD5E1",
        },
        primary: {
          DEFAULT: "#4F46E5",
          hover: "#6366F1",
          muted: "rgba(79, 70, 229, 0.08)",
          light: "#EEF2FF",
        },
        success: {
          DEFAULT: "#059669",
          muted: "rgba(5, 150, 105, 0.08)",
          light: "#ECFDF5",
        },
        warning: {
          DEFAULT: "#D97706",
          muted: "rgba(217, 119, 6, 0.08)",
          light: "#FFFBEB",
        },
        danger: {
          DEFAULT: "#DC2626",
          muted: "rgba(220, 38, 38, 0.08)",
          light: "#FEF2F2",
        },
        info: {
          DEFAULT: "#0891B2",
          muted: "rgba(8, 145, 178, 0.08)",
          light: "#ECFEFF",
        },
        text: {
          DEFAULT: "#0F172A",
          primary: "#0F172A",
          secondary: "#475569",
          muted: "#94A3B8",
        },
      },
      fontFamily: {
        display: ["var(--font-space-grotesk)", "Space Grotesk", "system-ui", "sans-serif"],
        body: ["var(--font-inter)", "Inter", "system-ui", "sans-serif"],
        mono: ["var(--font-jetbrains-mono)", "JetBrains Mono", "monospace"],
      },
      fontSize: {
        "display-lg": ["30px", { lineHeight: "36px", fontWeight: "700" }],
        "display-md": ["24px", { lineHeight: "30px", fontWeight: "600" }],
        "display-sm": ["18px", { lineHeight: "24px", fontWeight: "600" }],
        "body-lg": ["16px", { lineHeight: "24px" }],
        "body-md": ["14px", { lineHeight: "20px" }],
        "body-sm": ["12px", { lineHeight: "16px" }],
        "label": ["11px", { lineHeight: "16px", letterSpacing: "0.06em", fontWeight: "600" }],
      },
      spacing: {
        sidebar: "240px",
        "sidebar-collapsed": "68px",
        topbar: "64px",
        card: "20px",
        section: "16px",
        inline: "8px",
      },
      borderRadius: {
        card: "12px",
        button: "8px",
        badge: "6px",
        pill: "9999px",
      },
      boxShadow: {
        card: "0 1px 3px 0 rgb(0 0 0 / 0.04), 0 1px 2px -1px rgb(0 0 0 / 0.04)",
        "card-hover": "0 4px 12px 0 rgb(0 0 0 / 0.06), 0 2px 4px -2px rgb(0 0 0 / 0.04)",
        elevated: "0 10px 25px -5px rgb(0 0 0 / 0.08), 0 8px 10px -6px rgb(0 0 0 / 0.04)",
        glow: "0 0 20px rgba(79, 70, 229, 0.15)",
      },
      animation: {
        "fade-in": "fadeIn 0.3s ease-out",
        "slide-up": "slideUp 0.3s ease-out",
        "slide-down": "slideDown 0.2s ease-out",
        "scale-in": "scaleIn 0.15s ease-out",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        slideDown: {
          "0%": { opacity: "0", transform: "translateY(-4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        scaleIn: {
          "0%": { opacity: "0", transform: "scale(0.95)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
}
