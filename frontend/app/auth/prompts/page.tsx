"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { apiGet, apiPut, ApiError } from "@/lib/api";
import type { Prompt } from "@/lib/types";

interface Notice {
  kind: "success" | "error";
  message: string;
}

const REQUIRED = ["domain", "last_name", "gender", "template"] as const;
function localMissing(text: string): string[] {
  return REQUIRED.filter((p) => !text.includes(`{${p}}`));
}

export default function PromptsPage() {
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const [notice, setNotice] = useState<Notice | null>(null);
  const [showHistory, setShowHistory] = useState(false);

  const activeQuery = useQuery({
    queryKey: ["prompt-active"],
    queryFn: () => apiGet<Prompt>("/prompts/active"),
  });
  const historyQuery = useQuery({
    queryKey: ["prompt-history"],
    queryFn: () => apiGet<Prompt[]>("/prompts/history"),
    enabled: showHistory,
  });

  useEffect(() => {
    if (activeQuery.data) setText(activeQuery.data.text);
  }, [activeQuery.data]);

  const save = useMutation({
    mutationFn: () => apiPut<Prompt>("/prompts/active", { text }),
    onSuccess: async () => {
      setNotice({ kind: "success", message: "New prompt version is active." });
      await qc.invalidateQueries({ queryKey: ["prompt-active"] });
      await qc.invalidateQueries({ queryKey: ["prompt-history"] });
    },
    onError: (err) =>
      setNotice({
        kind: "error",
        message: err instanceof ApiError ? err.message : "Save failed.",
      }),
  });

  const missing = localMissing(text);
  const isDirty = activeQuery.data?.text !== text;

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Prompt</h1>
        <p className="text-sm text-muted-foreground">
          The single active prompt the LLM sees on every draft. Saving inserts a new version
          and deactivates the previous one — drafts already generated keep their snapshot.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Active prompt</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {activeQuery.isLoading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : (
            <>
              <Textarea
                rows={16}
                value={text}
                onChange={(e) => setText(e.target.value)}
                className="font-mono text-xs"
              />
              {missing.length > 0 ? (
                <p className="text-xs text-amber-700">
                  Missing placeholders: {missing.map((p) => `{${p}}`).join(", ")}. Generation
                  will reject a template that also lacks them.
                </p>
              ) : (
                <p className="text-xs text-emerald-700">All placeholders present.</p>
              )}
              {notice && (
                <p
                  className={
                    notice.kind === "error"
                      ? "text-sm text-destructive"
                      : "text-sm text-emerald-600"
                  }
                >
                  {notice.message}
                </p>
              )}
              <Button
                onClick={() => save.mutate()}
                disabled={save.isPending || !isDirty || !text.trim()}
              >
                {save.isPending ? "Saving…" : "Save new version"}
              </Button>
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>History</CardTitle>
          <Button variant="outline" size="sm" onClick={() => setShowHistory((v) => !v)}>
            {showHistory ? "Hide" : "Show"}
          </Button>
        </CardHeader>
        {showHistory && (
          <CardContent className="space-y-3">
            {historyQuery.isLoading && (
              <p className="text-sm text-muted-foreground">Loading…</p>
            )}
            {(historyQuery.data ?? []).map((p) => (
              <div key={p.id} className="rounded border p-3">
                <div className="mb-2 flex items-center gap-2">
                  {p.is_active && <Badge variant="default">active</Badge>}
                  <span className="text-xs text-muted-foreground">
                    saved {new Date(p.created_at).toLocaleString()}
                  </span>
                </div>
                <pre className="max-h-40 overflow-y-auto whitespace-pre-wrap text-xs text-muted-foreground">
                  {p.text}
                </pre>
              </div>
            ))}
            {historyQuery.data?.length === 0 && (
              <p className="text-sm text-muted-foreground">No history yet.</p>
            )}
          </CardContent>
        )}
      </Card>
    </div>
  );
}
