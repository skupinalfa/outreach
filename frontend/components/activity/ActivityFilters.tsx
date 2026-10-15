"use client";

import { useQuery } from "@tanstack/react-query";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { apiGet } from "@/lib/api";
import type { ActivityEventType, Contact, Organisation, Paginated } from "@/lib/types";

const EVENT_TYPES: ActivityEventType[] = [
  "lead_created",
  "enrichment_attempted",
  "draft_generated",
  "draft_regenerated",
  "draft_stored_in_mailbox",
  "mailbox_store_failed",
  "email_sent",
  "send_failed",
  "todo_created",
  "todo_completed",
  "todo_cancelled",
  "follow_up_scheduled",
  "status_changed",
];

const WINDOWS = [
  { value: "" as const, label: "All time" },
  { value: "today" as const, label: "Today" },
  { value: "last_7d" as const, label: "Last 7 days" },
  { value: "last_30d" as const, label: "Last 30 days" },
];

export type Window = "" | "today" | "last_7d" | "last_30d";

export interface ActivityFiltersState {
  eventTypes: ActivityEventType[];
  contactId: number | null;
  organisationId: number | null;
  window: Window;
}

interface Props {
  value: ActivityFiltersState;
  onChange: (next: ActivityFiltersState) => void;
}

export function ActivityFilters({ value, onChange }: Props) {
  const contactsQuery = useQuery({
    queryKey: ["contacts", "for-activity-filter"],
    queryFn: () => apiGet<Paginated<Contact>>("/contacts?limit=200"),
    staleTime: 60_000,
  });
  const orgsQuery = useQuery({
    queryKey: ["organisations", "for-activity-filter"],
    queryFn: () => apiGet<Paginated<Organisation>>("/organisations?limit=200"),
    staleTime: 60_000,
  });

  const toggleEventType = (t: ActivityEventType) => {
    const has = value.eventTypes.includes(t);
    onChange({
      ...value,
      eventTypes: has ? value.eventTypes.filter((x) => x !== t) : [...value.eventTypes, t],
    });
  };

  const reset = () =>
    onChange({ eventTypes: [], contactId: null, organisationId: null, window: "" });

  return (
    <div className="space-y-4 rounded-lg border p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">Filters</h2>
        <Button type="button" variant="ghost" size="sm" onClick={reset}>
          Reset
        </Button>
      </div>

      <div className="space-y-2">
        <Label className="text-xs text-muted-foreground">Event types</Label>
        <div className="flex flex-wrap gap-2">
          {EVENT_TYPES.map((t) => {
            const active = value.eventTypes.includes(t);
            return (
              <button
                key={t}
                type="button"
                onClick={() => toggleEventType(t)}
                className="focus:outline-none"
                aria-pressed={active}
              >
                <Badge variant={active ? "default" : "outline"} className="cursor-pointer">
                  {t}
                </Badge>
              </button>
            );
          })}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="space-y-1">
          <Label htmlFor="filter-contact" className="text-xs text-muted-foreground">
            Contact
          </Label>
          <select
            id="filter-contact"
            className="h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            value={value.contactId ?? ""}
            onChange={(e) =>
              onChange({
                ...value,
                contactId: e.target.value ? Number(e.target.value) : null,
              })
            }
          >
            <option value="">All contacts</option>
            {(contactsQuery.data?.items ?? []).map((c) => (
              <option key={c.id} value={c.id}>
                {c.first_name} {c.last_name}
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-1">
          <Label htmlFor="filter-org" className="text-xs text-muted-foreground">
            Organisation
          </Label>
          <select
            id="filter-org"
            className="h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            value={value.organisationId ?? ""}
            onChange={(e) =>
              onChange({
                ...value,
                organisationId: e.target.value ? Number(e.target.value) : null,
              })
            }
          >
            <option value="">All organisations</option>
            {(orgsQuery.data?.items ?? []).map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-1">
          <Label htmlFor="filter-window" className="text-xs text-muted-foreground">
            Time window
          </Label>
          <select
            id="filter-window"
            className="h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            value={value.window}
            onChange={(e) => onChange({ ...value, window: e.target.value as Window })}
          >
            {WINDOWS.map((w) => (
              <option key={w.value || "any"} value={w.value}>
                {w.label}
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
}

/** Serialise the current filters into query-string params for GET /activity. */
export function activityFilterQuery(state: ActivityFiltersState): URLSearchParams {
  const p = new URLSearchParams();
  for (const t of state.eventTypes) p.append("event_type", t);
  if (state.contactId != null) p.set("contact_id", String(state.contactId));
  if (state.organisationId != null) p.set("organisation_id", String(state.organisationId));
  if (state.window) p.set("window", state.window);
  return p;
}
