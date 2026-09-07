"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { Button } from "@/components/ui/button";
import { apiDelete, apiGet, ApiError } from "@/lib/api";

// Powers the FR-027a confirmation dialog: fetches counts from the /delete-impact
// endpoint, lists what will be removed, offers Delete + Cancel. Used by both
// organisation and contact delete flows (FR-027b).
export interface DeleteImpact {
  target: {
    kind: "organisation" | "contact";
    id: number;
    name: string;
  };
  counts: {
    contacts: number;
    drafts: number;
    sent_messages: number;
    open_todos: number;
  };
}

interface DeleteConfirmDialogProps {
  open: boolean;
  impactPath: string;
  deletePath: string;
  entityKind: "organisation" | "contact";
  entityName: string;
  onClose: () => void;
  onDeleted?: () => void;
  invalidateQueryKeys?: readonly unknown[][];
}

const COUNT_LABEL: Record<keyof DeleteImpact["counts"], { singular: string; plural: string }> = {
  contacts: { singular: "contact", plural: "contacts" },
  drafts: { singular: "draft", plural: "drafts" },
  sent_messages: { singular: "sent message", plural: "sent messages" },
  open_todos: { singular: "open todo", plural: "open todos" },
};

function nonZeroLines(counts: DeleteImpact["counts"]): string[] {
  const out: string[] = [];
  for (const key of Object.keys(counts) as Array<keyof DeleteImpact["counts"]>) {
    const n = counts[key];
    if (n <= 0) continue;
    const { singular, plural } = COUNT_LABEL[key];
    out.push(`${n} ${n === 1 ? singular : plural}`);
  }
  return out;
}

export function DeleteConfirmDialog({
  open,
  impactPath,
  deletePath,
  entityKind,
  entityName,
  onClose,
  onDeleted,
  invalidateQueryKeys,
}: DeleteConfirmDialogProps) {
  const qc = useQueryClient();

  const impact = useQuery({
    queryKey: ["delete-impact", impactPath],
    queryFn: () => apiGet<DeleteImpact>(impactPath),
    enabled: open,
    // Impact counts must reflect the *current* state — never cache stale values
    // (FR-037 + FR-027a: counts shown must match what the cascade will remove).
    staleTime: 0,
    gcTime: 0,
  });

  const remove = useMutation({
    mutationFn: () => apiDelete<void>(deletePath),
    onSuccess: async () => {
      if (invalidateQueryKeys) {
        await Promise.all(
          invalidateQueryKeys.map((key) => qc.invalidateQueries({ queryKey: key })),
        );
      }
      onDeleted?.();
      onClose();
    },
  });

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !remove.isPending) onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, remove.isPending, onClose]);

  if (!open) return null;

  const counts = impact.data?.counts;
  const lines = counts ? nonZeroLines(counts) : [];
  const errorMessage =
    remove.error instanceof ApiError
      ? remove.error.message
      : remove.isError
        ? "Delete failed."
        : null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="delete-confirm-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={remove.isPending ? undefined : onClose}
    >
      <div
        className="w-full max-w-md rounded-lg border bg-background p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="delete-confirm-title" className="text-lg font-semibold">
          Delete {entityKind} “{entityName}”?
        </h2>
        <div className="mt-3 text-sm text-muted-foreground">
          {impact.isLoading && <p>Checking what would be deleted…</p>}
          {impact.isError && (
            <p className="text-destructive">
              Could not load impact:{" "}
              {impact.error instanceof ApiError ? impact.error.message : "unknown error"}
            </p>
          )}
          {counts && (
            <>
              {lines.length === 0 ? (
                <p>Nothing else will be removed — this {entityKind} has no attached records.</p>
              ) : (
                <>
                  <p>This will permanently delete:</p>
                  <ul className="mt-2 list-disc space-y-1 pl-5">
                    {lines.map((line) => (
                      <li key={line}>{line}</li>
                    ))}
                  </ul>
                </>
              )}
              <p className="mt-3 text-xs">This cannot be undone.</p>
            </>
          )}
          {errorMessage && (
            <p className="mt-3 text-sm text-destructive">{errorMessage}</p>
          )}
        </div>

        <div className="mt-6 flex justify-end gap-2">
          <Button variant="outline" onClick={onClose} disabled={remove.isPending}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={() => remove.mutate()}
            disabled={impact.isLoading || impact.isError || remove.isPending}
          >
            {remove.isPending ? "Deleting…" : "Delete"}
          </Button>
        </div>
      </div>
    </div>
  );
}
