"use client";

import { useState } from "react";

import { ActivityBodyExpand } from "@/components/activity/ActivityBodyExpand";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { ActivityEventType, ActivityEventView } from "@/lib/types";

const EVENT_ICONS: Record<ActivityEventType, string> = {
  lead_created: "＋",
  enrichment_attempted: "🔍",
  draft_generated: "✎",
  draft_regenerated: "↻",
  draft_stored_in_mailbox: "📮",
  mailbox_store_failed: "⚠︎",
  email_sent: "✉︎",
  send_failed: "⚠︎",
  todo_created: "☐",
  todo_completed: "☑",
  todo_cancelled: "✕",
  follow_up_scheduled: "⏱",
  status_changed: "→",
};

const EVENT_LABELS: Record<ActivityEventType, string> = {
  lead_created: "Lead created",
  enrichment_attempted: "Enrichment attempted",
  draft_generated: "Draft generated",
  draft_regenerated: "Draft regenerated",
  draft_stored_in_mailbox: "Draft saved to mailbox",
  mailbox_store_failed: "Mailbox save failed",
  email_sent: "Email sent",
  send_failed: "Send failed",
  todo_created: "Todo created",
  todo_completed: "Todo completed",
  todo_cancelled: "Todo cancelled",
  follow_up_scheduled: "Follow-up scheduled",
  status_changed: "Status changed",
};

interface Props {
  event: ActivityEventView;
  /** When true, show contact + organisation on the row (global timeline). */
  showContact?: boolean;
  onSelectContact?: (contactId: number) => void;
}

export function ActivityRow({ event, showContact = false, onSelectContact }: Props) {
  const [expanded, setExpanded] = useState(false);
  const hasSnapshot = event.message_snapshot !== null;

  return (
    <li className="border-b py-3 last:border-b-0">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 text-lg leading-none" aria-hidden="true">
          {EVENT_ICONS[event.event_type]}
        </span>
        <div className="flex-1 space-y-1">
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
            <span className="font-medium">{EVENT_LABELS[event.event_type]}</span>
            <Badge variant="outline" className="text-[10px] uppercase">
              {event.actor}
            </Badge>
            {showContact && (
              <button
                type="button"
                className="text-sm text-primary underline-offset-2 hover:underline"
                onClick={() => onSelectContact?.(event.contact.id)}
              >
                {event.contact.first_name} {event.contact.last_name}
                {event.organisation && (
                  <span className="text-muted-foreground"> · {event.organisation.name}</span>
                )}
              </button>
            )}
            <time className="ml-auto text-xs text-muted-foreground">
              {new Date(event.occurred_at).toLocaleString()}
            </time>
          </div>
          <p className="text-sm text-muted-foreground">{event.summary}</p>
          {hasSnapshot && (
            <>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setExpanded((v) => !v)}
              >
                {expanded ? "Hide message" : "Show message"}
              </Button>
              {expanded && event.message_snapshot && (
                <ActivityBodyExpand snapshot={event.message_snapshot} />
              )}
            </>
          )}
        </div>
      </div>
    </li>
  );
}
