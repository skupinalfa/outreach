"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { apiGet } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { DashboardActivity, DashboardOverview } from "@/lib/types";

function deltaChip(value: number) {
  if (value === 0) {
    return <span className="text-xs text-muted-foreground">±0 vs prior</span>;
  }
  const positive = value > 0;
  return (
    <span
      className={cn(
        "text-xs",
        positive ? "text-emerald-600" : "text-destructive",
      )}
    >
      {positive ? "+" : ""}
      {value} vs prior
    </span>
  );
}

interface MetricProps {
  label: string;
  value: number;
  delta?: number;
  href?: string;
  hint?: string;
}

function Metric({ label, value, delta, href, hint }: MetricProps) {
  const body = (
    <Card className={cn(href && "transition-colors hover:bg-muted/50")}>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{label}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-semibold">{value}</div>
        {hint && <div className="mt-1 text-xs text-muted-foreground">{hint}</div>}
        {delta !== undefined && <div className="mt-1">{deltaChip(delta)}</div>}
      </CardContent>
    </Card>
  );
  return href ? <Link href={href}>{body}</Link> : body;
}

function activityRow(a: DashboardActivity | undefined, windowLabel: string) {
  if (!a) return null;
  return (
    <div className="space-y-3">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        Activity — last {windowLabel}
      </h2>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Metric
          label="Leads added"
          value={a.leads_added}
          delta={a.delta_vs_prior.leads_added}
          href="/auth/contacts"
        />
        <Metric
          label="Drafts generated"
          value={a.drafts_generated}
          delta={a.delta_vs_prior.drafts_generated}
          href="/auth/contacts?status=enriched"
        />
        <Metric
          label="Emails sent"
          value={a.emails_sent}
          delta={a.delta_vs_prior.emails_sent}
          href="/auth/contacts?status=contacted"
        />
        <Metric
          label="Follow-ups due"
          value={a.follow_ups_due}
          delta={a.delta_vs_prior.follow_ups_due}
          href="/auth/todos"
        />
        <Metric
          label="Replies logged"
          value={a.replies_logged}
          delta={a.delta_vs_prior.replies_logged}
          href="/auth/contacts?status=replied"
        />
      </div>
    </div>
  );
}

function OnboardingEmpty() {
  return (
    <div className="mx-auto max-w-xl space-y-4 pt-10 text-center">
      <h1 className="text-2xl font-semibold">Let&apos;s get you started</h1>
      <p className="text-muted-foreground">
        No contacts yet. Set your credentials, then add your first lead — the dashboard
        fills in as you work.
      </p>
      <div className="flex justify-center gap-3">
        <Link
          href="/auth/settings"
          className="inline-flex h-10 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          Set credentials
        </Link>
        <Link
          href="/auth/leads"
          className="inline-flex h-10 items-center rounded-md border border-input bg-background px-4 text-sm font-medium hover:bg-muted"
        >
          Add a lead
        </Link>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["dashboard-overview"],
    queryFn: () => apiGet<DashboardOverview>("/dashboard/overview"),
    refetchInterval: 60_000,
  });

  if (isLoading) return <p>Loading…</p>;
  if (isError || !data) return <p className="text-destructive">Could not load dashboard.</p>;

  if (data.onboarding_required) return <OnboardingEmpty />;

  const funnelSent = data.funnel_30d?.sent ?? 0;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <p className="text-sm text-muted-foreground">
          The current state of your pipeline. Cards link to the underlying screens.
        </p>
      </div>

      <div className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Todos
        </h2>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <Metric
            label="Overdue"
            value={data.todos?.overdue_count ?? 0}
            href="/auth/todos"
          />
          <Metric
            label="Due today"
            value={data.todos?.due_today_count ?? 0}
            href="/auth/todos"
          />
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Next action
              </CardTitle>
            </CardHeader>
            <CardContent>
              {data.todos?.next_action ? (
                <Link
                  href={`/auth/todos/${data.todos.next_action.todo_id}`}
                  className="hover:underline"
                >
                  <div className="font-medium">{data.todos.next_action.title}</div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    due {new Date(data.todos.next_action.due_at).toLocaleString()}
                  </div>
                </Link>
              ) : (
                <div className="text-sm text-muted-foreground">Nothing open.</div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {activityRow(data.activity, "7 days")}
      {activityRow(data.activity_30d, "30 days")}

      <div className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Response funnel — last 30 days
        </h2>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          <Metric label="Sent" value={data.funnel_30d?.sent ?? 0} />
          <Metric
            label="Replied"
            value={data.funnel_30d?.replied ?? 0}
            hint={
              funnelSent
                ? `${((data.funnel_30d!.reply_rate) * 100).toFixed(1)}% reply rate`
                : undefined
            }
          />
          <Metric
            label="Meeting booked"
            value={data.funnel_30d?.meeting_booked ?? 0}
            hint={
              funnelSent
                ? `${((data.funnel_30d!.booking_rate) * 100).toFixed(1)}% booking rate`
                : undefined
            }
          />
        </div>
      </div>
    </div>
  );
}
