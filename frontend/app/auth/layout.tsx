import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";

import AppShell from "@/components/app-shell";
import { SettingsCTABanner } from "@/components/settings-cta";

interface AuthMe {
  authenticated: boolean;
  master_password_set: boolean;
}

async function fetchAuthMe(cookieHeader: string): Promise<AuthMe> {
  const base =
    process.env.INTERNAL_API_URL ??
    process.env.NEXT_PUBLIC_API_URL ??
    "http://localhost:8000";
  const res = await fetch(`${base}/api/v1/auth/me`, {
    headers: { cookie: cookieHeader },
    cache: "no-store",
  });
  if (!res.ok) {
    return { authenticated: false, master_password_set: false };
  }
  return (await res.json()) as AuthMe;
}

export default async function AuthLayout({ children }: { children: ReactNode }) {
  const jar = await cookies();
  const cookieHeader = jar.toString();
  const me = await fetchAuthMe(cookieHeader);

  if (!me.master_password_set) redirect("/bootstrap");
  if (!me.authenticated) redirect("/login");

  return (
    <AppShell>
      <SettingsCTABanner />
      {children}
    </AppShell>
  );
}
