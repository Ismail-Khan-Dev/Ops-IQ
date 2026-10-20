"use client";

import React, { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { useRouter } from "next/navigation";
import {
  Search,
  LayoutDashboard,
  Bot,
  ShoppingCart,
  Package,
  Star,
  BarChart3,
  Store,
  Shield,
  Settings,
  Zap,
  Plus,
  RefreshCw,
  FileText,
  Key,
  ScrollText,
  X,
} from "lucide-react";

interface Command {
  id: string;
  label: string;
  icon: React.ReactNode;
  shortcut?: string;
  category: string;
  action: () => void;
}

interface CommandPaletteContextValue {
  open: boolean;
  setOpen: (open: boolean) => void;
}

const CommandPaletteContext = React.createContext<CommandPaletteContextValue>({
  open: false,
  setOpen: () => {},
});

export function useCommandPalette(): CommandPaletteContextValue {
  return React.useContext(CommandPaletteContext);
}

export function CommandPaletteProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  return (
    <CommandPaletteContext.Provider value={{ open, setOpen }}>
      {children}
    </CommandPaletteContext.Provider>
  );
}

function getCommands(
  router: ReturnType<typeof useRouter>,
  setOpen: (v: boolean) => void
): Command[] {
  const nav = (href: string) => {
    router.push(href);
    setOpen(false);
  };

  return [
    {
      id: "nav-dashboard",
      label: "Dashboard",
      icon: <LayoutDashboard size={18} />,
      shortcut: "⌘1",
      category: "Navigation",
      action: () => nav("/"),
    },
    {
      id: "nav-agents",
      label: "Agents",
      icon: <Bot size={18} />,
      shortcut: "⌘2",
      category: "Navigation",
      action: () => nav("/agents"),
    },
    {
      id: "nav-analytics",
      label: "Analytics",
      icon: <BarChart3 size={18} />,
      shortcut: "⌘3",
      category: "Navigation",
      action: () => nav("/analytics"),
    },
    {
      id: "nav-orders",
      label: "Orders",
      icon: <ShoppingCart size={18} />,
      shortcut: "⌘4",
      category: "Navigation",
      action: () => nav("/orders"),
    },
    {
      id: "nav-products",
      label: "Products",
      icon: <Package size={18} />,
      shortcut: "⌘5",
      category: "Navigation",
      action: () => nav("/products"),
    },
    {
      id: "nav-cart-recovery",
      label: "Cart Recovery",
      icon: <Zap size={18} />,
      shortcut: "⌘6",
      category: "Navigation",
      action: () => nav("/cart-recovery"),
    },
    {
      id: "nav-reviews",
      label: "Reviews",
      icon: <Star size={18} />,
      shortcut: "⌘7",
      category: "Navigation",
      action: () => nav("/reviews"),
    },
    {
      id: "nav-support",
      label: "Support",
      icon: <ScrollText size={18} />,
      shortcut: "⌘8",
      category: "Navigation",
      action: () => nav("/support"),
    },
    {
      id: "nav-security",
      label: "Security",
      icon: <Shield size={18} />,
      shortcut: "⌘9",
      category: "Navigation",
      action: () => nav("/security"),
    },
    {
      id: "nav-settings",
      label: "Settings",
      icon: <Settings size={18} />,
      shortcut: "⌘0",
      category: "Navigation",
      action: () => nav("/settings"),
    },
    {
      id: "nav-shopify",
      label: "Shopify",
      icon: <Store size={18} />,
      category: "Navigation",
      action: () => nav("/shopify"),
    },
    {
      id: "action-deploy",
      label: "Deploy New Agent",
      icon: <Plus size={18} />,
      shortcut: "⌘⇧D",
      category: "Actions",
      action: () => nav("/agents"),
    },
    {
      id: "action-sync",
      label: "Sync Shopify",
      icon: <RefreshCw size={18} />,
      category: "Actions",
      action: () => nav("/shopify"),
    },
    {
      id: "action-audit",
      label: "Run Audit",
      icon: <Shield size={18} />,
      category: "Actions",
      action: () => nav("/analytics"),
    },
    {
      id: "action-export",
      label: "Export Report",
      icon: <FileText size={18} />,
      category: "Actions",
      action: () => nav("/analytics"),
    },
    {
      id: "quick-logs",
      label: "View Logs",
      icon: <ScrollText size={18} />,
      category: "Quick",
      action: () => nav("/security"),
    },
  ];
}

export default function CommandPalette() {
  const router = useRouter();
  const { open, setOpen } = useCommandPalette();
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const commands = useMemo(() => getCommands(router, setOpen), [router, setOpen]);

  const filtered = useMemo(() => {
    if (!query.trim()) return commands;
    const q = query.toLowerCase();
    return commands.filter(
      (c) =>
        c.label.toLowerCase().includes(q) ||
        c.category.toLowerCase().includes(q)
    );
  }, [commands, query]);

  const grouped = useMemo(() => {
    const groups: Record<string, Command[]> = {};
    for (const cmd of filtered) {
      if (!groups[cmd.category]) groups[cmd.category] = [];
      groups[cmd.category].push(cmd);
    }
    return groups;
  }, [filtered]);

  const flatList = useMemo(() => filtered, [filtered]);

  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 50);
    } else {
      setQuery("");
      setSelectedIndex(0);
    }
  }, [open]);

  useEffect(() => {
    if (selectedIndex >= 0 && listRef.current) {
      const items = listRef.current.querySelectorAll("[data-command-item]");
      items[selectedIndex]?.scrollIntoView({ block: "nearest" });
    }
  }, [selectedIndex]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      switch (e.key) {
        case "ArrowDown":
          e.preventDefault();
          setSelectedIndex((i) => (i + 1) % flatList.length);
          break;
        case "ArrowUp":
          e.preventDefault();
          setSelectedIndex((i) => (i - 1 + flatList.length) % flatList.length);
          break;
        case "Enter":
          e.preventDefault();
          if (flatList[selectedIndex]) {
            flatList[selectedIndex].action();
          }
          break;
        case "Escape":
          e.preventDefault();
          setOpen(false);
          break;
      }
    },
    [flatList, selectedIndex, setOpen]
  );

  if (!open) return null;

  let runningIndex = -1;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh]">
      <div
        className="absolute inset-0 bg-void/60 backdrop-blur-sm"
        onClick={() => setOpen(false)}
      />
      <div className="relative w-full max-w-lg border border-border bg-surface rounded-2xl shadow-2xl overflow-hidden">
        <div className="flex items-center gap-3 px-4 py-3 border-b border-border">
          <Search size={18} className="text-text-muted shrink-0" />
          <input
            ref={inputRef}
            type="text"
            placeholder="Type a command..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            className="flex-1 bg-transparent text-text-primary placeholder:text-text-muted font-mono text-sm outline-none"
          />
          <button
            onClick={() => setOpen(false)}
            className="p-1 rounded-md text-text-muted hover:text-text-primary hover:bg-white/5 transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        <div ref={listRef} className="max-h-80 overflow-y-auto py-2">
          {flatList.length === 0 && (
            <div className="px-4 py-8 text-center text-text-muted text-sm">
              No commands found.
            </div>
          )}

          {Object.entries(grouped).map(([category, commands]) => (
            <div key={category}>
              <div className="px-4 py-1.5 text-xs font-display font-medium text-text-muted uppercase tracking-wider">
                {category}
              </div>
              {commands.map((cmd) => {
                runningIndex += 1;
                const idx = runningIndex;
                const isSelected = idx === selectedIndex;
                return (
                  <button
                    key={cmd.id}
                    data-command-item
                    onClick={() => cmd.action()}
                    onMouseEnter={() => setSelectedIndex(idx)}
                    className={`w-full flex items-center gap-3 px-4 py-2 text-sm transition-colors ${
                      isSelected
                        ? "bg-primary/10 text-text-primary"
                        : "text-text-secondary hover:bg-white/5"
                    }`}
                  >
                    <span
                      className={`shrink-0 ${
                        isSelected ? "text-primary" : "text-text-muted"
                      }`}
                    >
                      {cmd.icon}
                    </span>
                    <span className="flex-1 text-left font-display">
                      {cmd.label}
                    </span>
                    {cmd.shortcut && (
                      <span className="text-xs font-mono text-text-muted bg-white/5 px-1.5 py-0.5 rounded">
                        {cmd.shortcut}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          ))}
        </div>

        <div className="flex items-center gap-4 px-4 py-2 border-t border-border text-xs text-text-muted font-mono">
          <span className="flex items-center gap-1">
            <kbd className="px-1 py-0.5 rounded bg-white/5 border border-border text-[10px]">↑↓</kbd>
            navigate
          </span>
          <span className="flex items-center gap-1">
            <kbd className="px-1 py-0.5 rounded bg-white/5 border border-border text-[10px]">↵</kbd>
            select
          </span>
          <span className="flex items-center gap-1">
            <kbd className="px-1 py-0.5 rounded bg-white/5 border border-border text-[10px]">esc</kbd>
            close
          </span>
        </div>
      </div>
    </div>
  );
}
