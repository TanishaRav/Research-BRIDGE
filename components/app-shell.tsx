"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import {
  ClipboardList,
  FlaskConical,
  LayoutDashboard,
  Menu,
  ShieldCheck,
  X,
} from "lucide-react";
import { useDemo } from "@/lib/demo-context";
import type { DemoRole } from "@/lib/types";
import { cn } from "@/lib/format";
import { RoleSwitcher } from "./role-switcher";

interface NavItem {
  href: string;
  label: string;
}

const NAV: Record<DemoRole, NavItem[]> = {
  student: [
    { href: "/student", label: "Dashboard" },
    { href: "/student/profile", label: "Profile" },
    { href: "/student/projects", label: "Projects" },
    { href: "/student/outcome", label: "Placement & roadmap" },
  ],
  faculty: [
    { href: "/faculty", label: "Overview" },
    { href: "/faculty/projects", label: "Projects" },
    { href: "/faculty/candidates", label: "Assigned candidates" },
  ],
  admin: [
    { href: "/admin", label: "Overview" },
    { href: "/admin/data", label: "Data & import" },
    { href: "/admin/run", label: "Configure & run" },
    { href: "/admin/evidence", label: "Fairness evidence" },
    { href: "/admin/audit", label: "Audit timeline" },
  ],
};

const ROLE_META: Record<DemoRole, { label: string; icon: typeof LayoutDashboard }> = {
  student: { label: "Student", icon: LayoutDashboard },
  faculty: { label: "Faculty", icon: FlaskConical },
  admin: { label: "EUReCA Admin", icon: ShieldCheck },
};

export function AppShell({ children }: { children: React.ReactNode }) {
  const { identity, personaLabel, notice } = useDemo();
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  const role: DemoRole = identity?.role ?? "student";
  const items = NAV[role];
  const Meta = ROLE_META[role];

  const navList = (
    <nav aria-label="Primary" className="flex flex-col gap-1">
      {items.map((item) => {
        const active = pathname === item.href;
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            onClick={() => setMobileOpen(false)}
            className={cn(
              "rounded-md px-3 py-2 text-sm font-medium transition-colors",
              active
                ? "bg-accent-soft text-accent-pressed"
                : "text-ink-secondary hover:bg-subtle hover:text-ink",
            )}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );

  const brand = (
    <div className="flex items-center gap-3">
      <span className="grid h-9 w-9 place-items-center rounded-md border border-divider bg-surface font-display text-sm font-bold text-accent">
        RB
      </span>
      <div className="leading-tight">
        <p className="font-display text-sm font-semibold text-ink">ResearchBridge</p>
        <p className="text-xs text-ink-muted">Synthetic EUReCA demo</p>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[256px_1fr]">
      {/* Mobile top bar */}
      <header className="flex items-center justify-between border-b border-divider bg-surface px-4 py-3 lg:hidden">
        {brand}
        <button
          type="button"
          className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-md border border-divider"
          aria-expanded={mobileOpen}
          aria-controls="mobile-nav"
          onClick={() => setMobileOpen((open) => !open)}
        >
          {mobileOpen ? <X size={18} /> : <Menu size={18} />}
          <span className="sr-only">Toggle navigation</span>
        </button>
      </header>

      {mobileOpen ? (
        <div
          id="mobile-nav"
          className="border-b border-divider bg-surface px-4 py-4 lg:hidden"
        >
          <RoleSwitcher />
          <div className="mt-4">{navList}</div>
        </div>
      ) : null}

      {/* Desktop sidebar */}
      <aside className="hidden border-r border-divider bg-surface lg:flex lg:flex-col">
        <div className="border-b border-divider px-5 py-5">{brand}</div>
        <div className="border-b border-divider px-5 py-4">
          <RoleSwitcher />
        </div>
        <div className="flex items-center gap-2 px-5 py-3 text-xs text-ink-muted">
          <Meta.icon size={14} />
          <span>{Meta.label} · {personaLabel(identity)}</span>
        </div>
        <div className="flex-1 overflow-y-auto px-3 py-2">{navList}</div>
        <p className="border-t border-divider px-5 py-4 text-xs leading-relaxed text-ink-muted">
          {notice || "The role switcher selects seeded demo personas. It is not authentication."}
        </p>
        <Link
          href="/about"
          className="border-t border-divider px-5 py-3 text-xs font-medium text-ink-secondary hover:text-ink"
        >
          About & methodology
        </Link>
      </aside>

      <main
        id="main-content"
        tabIndex={-1}
        className="min-w-0 px-4 py-6 sm:px-6 lg:px-10 lg:py-8"
      >
        <div className="mx-auto w-full max-w-5xl">{children}</div>
      </main>
    </div>
  );
}

export function PageHeader({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string | undefined;
  title: string;
  description?: string | undefined;
  action?: React.ReactNode | undefined;
}) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
        <h1 className="text-[1.75rem] leading-tight">{title}</h1>
        {description ? (
          <p className="mt-2 max-w-2xl text-sm text-ink-secondary">{description}</p>
        ) : null}
      </div>
      {action}
    </header>
  );
}

export { ClipboardList };
