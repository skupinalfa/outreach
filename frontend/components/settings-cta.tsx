"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { ApiError, onApiError } from "@/lib/api";

type Service = "hunter" | "openai" | "smtp";

interface Notice {
  service: Service;
  message: string;
}

function inferService(err: ApiError, path: string): Service | null {
  const msg = err.message.toLowerCase();
  if (path.includes("/enrich") || path.includes("hunter") || msg.includes("hunter")) {
    return "hunter";
  }
  if (path.includes("/drafts") || path.includes("openai") || msg.includes("openai")) {
    return "openai";
  }
  if (path.includes("/send") || path.includes("smtp") || msg.includes("smtp")) {
    return "smtp";
  }
  return null;
}

const LABEL: Record<Service, string> = {
  hunter: "Hunter",
  openai: "OpenAI",
  smtp: "outbound mail",
};

/**
 * Watches API responses. When any request fails with `credential_not_set`, drops a
 * dismissable banner at the top of the app-shell with a deep link into Settings, so the
 * operator is one click away from fixing the underlying problem (FR-021).
 */
export function SettingsCTABanner() {
  const [notice, setNotice] = useState<Notice | null>(null);

  useEffect(() => {
    return onApiError((err, path) => {
      if (err.code !== "credential_not_set") return;
      const service = inferService(err, path);
      if (!service) return;
      setNotice({ service, message: err.message });
    });
  }, []);

  if (!notice) return null;

  return (
    <div
      role="alert"
      className="flex items-center justify-between gap-3 border-b border-amber-200 bg-amber-50 px-6 py-3 text-sm text-amber-900"
    >
      <div>
        <strong className="font-medium">Set your {LABEL[notice.service]} credentials</strong>
        <span className="ml-2 text-amber-800">in Settings — {notice.message}</span>
      </div>
      <div className="flex items-center gap-2">
        <Link
          href={`/auth/settings?highlight=${notice.service}`}
          className="inline-flex h-9 items-center rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          Open Settings
        </Link>
        <Button size="sm" variant="ghost" onClick={() => setNotice(null)}>
          Dismiss
        </Button>
      </div>
    </div>
  );
}
