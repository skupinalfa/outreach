"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { apiDelete, apiGet, apiPatch, apiPost, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { Template } from "@/lib/types";

interface Notice {
  kind: "success" | "error";
  message: string;
}

// Live placeholder lint in the editor — mirrors the backend `placeholder_validator`.
const REQUIRED = ["domain", "last_name", "gender", "template"] as const;
function localMissing(body: string): string[] {
  return REQUIRED.filter((p) => !body.includes(`{${p}}`));
}

interface DraftForm {
  name: string;
  subject_hint: string;
  body: string;
}

const EMPTY: DraftForm = { name: "", subject_hint: "", body: "" };

export default function TemplatesPage() {
  const qc = useQueryClient();
  const [includeArchived, setIncludeArchived] = useState(false);
  const [editing, setEditing] = useState<Template | "new" | null>(null);
  const [draft, setDraft] = useState<DraftForm>(EMPTY);
  const [notice, setNotice] = useState<Notice | null>(null);

  const listQuery = useQuery({
    queryKey: ["templates", includeArchived],
    queryFn: () =>
      apiGet<Template[]>(`/templates?include_archived=${includeArchived}`),
  });

  useEffect(() => {
    if (editing === "new") {
      setDraft(EMPTY);
    } else if (editing) {
      setDraft({
        name: editing.name,
        subject_hint: editing.subject_hint ?? "",
        body: editing.body,
      });
    }
  }, [editing]);

  const save = useMutation({
    mutationFn: async () => {
      const payload = {
        name: draft.name,
        subject_hint: draft.subject_hint || null,
        body: draft.body,
      };
      if (editing === "new") {
        return apiPost<Template>("/templates", payload);
      }
      if (editing) {
        return apiPatch<Template>(`/templates/${editing.id}`, payload);
      }
      throw new Error("no editor open");
    },
    onSuccess: async () => {
      setNotice({ kind: "success", message: "Template saved." });
      setEditing(null);
      await qc.invalidateQueries({ queryKey: ["templates"] });
    },
    onError: (err) =>
      setNotice({
        kind: "error",
        message: err instanceof ApiError ? err.message : "Save failed.",
      }),
  });

  const remove = useMutation({
    mutationFn: (id: number) => apiDelete<void>(`/templates/${id}`),
    onSuccess: async () => {
      setNotice({
        kind: "success",
        message:
          "Deleted (or archived if it was referenced by an existing draft).",
      });
      await qc.invalidateQueries({ queryKey: ["templates"] });
    },
    onError: (err) =>
      setNotice({
        kind: "error",
        message: err instanceof ApiError ? err.message : "Delete failed.",
      }),
  });

  const missing = localMissing(draft.body);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Templates</h1>
          <p className="text-sm text-muted-foreground">
            The email skeletons the LLM uses. Include the four placeholders so generation can
            personalise the message.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            <input
              type="checkbox"
              checked={includeArchived}
              onChange={(e) => setIncludeArchived(e.target.checked)}
            />
            Show archived
          </label>
          <Button onClick={() => setEditing("new")}>New template</Button>
        </div>
      </div>

      {notice && (
        <p
          className={
            notice.kind === "error" ? "text-sm text-destructive" : "text-sm text-emerald-600"
          }
        >
          {notice.message}
        </p>
      )}

      {editing && (
        <Card>
          <CardHeader>
            <CardTitle>
              {editing === "new" ? "New template" : `Edit "${editing.name}"`}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-2">
              <Label htmlFor="tpl-name">Name</Label>
              <Input
                id="tpl-name"
                value={draft.name}
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="tpl-subject">Subject hint (optional)</Label>
              <Input
                id="tpl-subject"
                value={draft.subject_hint}
                onChange={(e) => setDraft({ ...draft, subject_hint: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="tpl-body">Body</Label>
              <Textarea
                id="tpl-body"
                rows={16}
                value={draft.body}
                onChange={(e) => setDraft({ ...draft, body: e.target.value })}
              />
              {missing.length > 0 ? (
                <p className="text-xs text-amber-700">
                  Missing placeholders: {missing.map((p) => `{${p}}`).join(", ")}. Generation
                  will fail unless the active prompt supplies them.
                </p>
              ) : (
                <p className="text-xs text-emerald-700">All placeholders present.</p>
              )}
            </div>
            <div className="flex gap-3">
              <Button
                onClick={() => save.mutate()}
                disabled={save.isPending || !draft.name || !draft.body}
              >
                {save.isPending ? "Saving…" : "Save"}
              </Button>
              <Button variant="outline" onClick={() => setEditing(null)}>
                Cancel
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="rounded-md border">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-left">
            <tr>
              <th className="px-4 py-2 font-medium">Name</th>
              <th className="px-4 py-2 font-medium">Placeholders</th>
              <th className="px-4 py-2 font-medium">Status</th>
              <th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody>
            {listQuery.isLoading && (
              <tr>
                <td colSpan={4} className="px-4 py-4 text-muted-foreground">
                  Loading…
                </td>
              </tr>
            )}
            {(listQuery.data ?? []).map((t) => (
              <tr
                key={t.id}
                className={cn("border-t", t.is_archived && "text-muted-foreground")}
              >
                <td className="px-4 py-2 font-medium">{t.name}</td>
                <td className="px-4 py-2">
                  {t.missing_placeholders.length === 0 ? (
                    <Badge variant="secondary">complete</Badge>
                  ) : (
                    <Badge variant="destructive">
                      missing {t.missing_placeholders.join(", ")}
                    </Badge>
                  )}
                </td>
                <td className="px-4 py-2">
                  {t.is_archived ? <Badge variant="outline">archived</Badge> : "active"}
                </td>
                <td className="px-4 py-2 text-right">
                  <Button variant="ghost" size="sm" onClick={() => setEditing(t)}>
                    Edit
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => remove.mutate(t.id)}>
                    Delete
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
