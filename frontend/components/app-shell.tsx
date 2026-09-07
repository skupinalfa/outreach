"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { apiPost } from "@/lib/api";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/auth/dashboard", label: "Dashboard" },
  { href: "/auth/todos", label: "Todos" },
  { href: "/auth/leads", label: "Leads" },
  { href: "/auth/organisations", label: "Organisations" },
  { href: "/auth/contacts", label: "Contacts" },
  { href: "/auth/templates", label: "Templates" },
  { href: "/auth/prompts", label: "Prompts" },
  { href: "/auth/settings", label: "Settings" },
];

export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  async function onLogout() {
    await apiPost("/auth/logout");
    window.location.href = "/login";
  }

  return (
    <div className="flex min-h-screen">
      <aside className="w-56 border-r bg-muted/30 p-4">
        <div className="mb-6 text-lg font-semibold">ColdMail</div>
        <nav className="flex flex-col gap-1">
          {NAV.map((item) => {
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "rounded-md px-3 py-2 text-sm",
                  active ? "bg-primary text-primary-foreground" : "hover:bg-muted",
                )}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        <Button variant="outline" className="mt-6 w-full" onClick={onLogout}>
          Log out
        </Button>
      </aside>
      <section className="flex-1 p-6">{children}</section>
    </div>
  );
}
