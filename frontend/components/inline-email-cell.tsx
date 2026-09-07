"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { QueryKey } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiPatch, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { Contact } from "@/lib/types";

interface Props {
  contactId: number;
  currentEmail: string | null;
  /** Query keys to invalidate after a successful save, so the row re-renders. */
  invalidateKeys?: QueryKey[];
  /** Optional wrapper class — tune density in a table cell vs. an inline row. */
  className?: string;
}

/**
 * Row-scoped inline email editor for list contexts.
 *
 * Implements FR-006a everywhere a contact is presented: shows an `<Input>` pre-filled with
 * the current email + a Save button that PATCHes `/contacts/{id}`. The button is disabled
 * while the draft matches the server value (nothing to save) and while the request is in
 * flight. An empty string sends `email: null` to clear the field.
 *
 * Errors are surfaced as a small red text under the row rather than a toast — a toast per
 * row would be noisy when the operator makes multiple edits in a list.
 */
export function InlineEmailCell({ contactId, currentEmail, invalidateKeys, className }: Props) {
  const qc = useQueryClient();
  const [draft, setDraft] = useState(currentEmail ?? "");
  const [error, setError] = useState<string | null>(null);
  const [lastSyncedFrom, setLastSyncedFrom] = useState(currentEmail ?? "");

  // Auto-sync the draft when the server value changes *and* the operator hasn't started
  // typing over it. Prevents a background refetch (e.g. after enrichment on another tab)
  // from silently wiping unsaved input.
  useEffect(() => {
    const next = currentEmail ?? "";
    if (draft === lastSyncedFrom) {
      setDraft(next);
    }
    setLastSyncedFrom(next);
    // Intentionally omit `draft` from deps — this hook reacts to server changes only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentEmail]);

  const save = useMutation({
    mutationFn: () =>
      apiPatch<Contact>(`/contacts/${contactId}`, { email: draft.trim() || null }),
    onSuccess: async () => {
      setError(null);
      for (const key of invalidateKeys ?? []) {
        await qc.invalidateQueries({ queryKey: key });
      }
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : "Save failed.");
    },
  });

  const dirty = (draft.trim() || null) !== (currentEmail ?? null);

  return (
    <div className={cn("space-y-1", className)}>
      <div className="flex items-center gap-2">
        <Input
          type="email"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="name@company.com"
          className="h-8 font-mono text-xs"
        />
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={!dirty || save.isPending}
          onClick={() => save.mutate()}
        >
          {save.isPending ? "…" : "Save"}
        </Button>
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}
