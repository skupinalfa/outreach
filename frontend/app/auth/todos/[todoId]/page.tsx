"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { apiDelete, apiGet, apiPost, ApiError } from "@/lib/api";
import type {
  Contact,
  Draft,
  Organisation,
  SaveToMailboxResponse,
  SentMessage,
  SettingsView,
  Todo,
} from "@/lib/types";

interface Notice {
  kind: "success" | "error";
  message: string;
}

export default function TodoDetailPage() {
  const params = useParams<{ todoId: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const todoId = Number(params.todoId);

  const todoQuery = useQuery({
    queryKey: ["todo", todoId],
    queryFn: () => apiGet<Todo>(`/todos/${todoId}`),
    enabled: !Number.isNaN(todoId),
  });

  const contactQuery = useQuery({
    queryKey: ["contact", todoQuery.data?.contact_id],
    queryFn: () => apiGet<Contact>(`/contacts/${todoQuery.data!.contact_id}`),
    enabled: !!todoQuery.data,
  });

  const orgQuery = useQuery({
    queryKey: ["organisation", contactQuery.data?.organisation_id],
    queryFn: () =>
      apiGet<Organisation>(`/organisations/${contactQuery.data!.organisation_id}`),
    enabled: !!contactQuery.data,
  });

  const draftQuery = useQuery({
    queryKey: ["draft", todoQuery.data?.contact_id],
    queryFn: async () => {
      try {
        return await apiGet<Draft>(`/contacts/${todoQuery.data!.contact_id}/draft`);
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) return null;
        throw err;
      }
    },
    enabled: !!todoQuery.data && todoQuery.data.type === "send",
  });

  const settingsQuery = useQuery({
    queryKey: ["settings"],
    queryFn: () => apiGet<SettingsView>("/settings"),
  });

  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);
  const [savingToMailbox, setSavingToMailbox] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);

  useEffect(() => {
    if (draftQuery.data) {
      setSubject(draftQuery.data.subject);
      setBody(draftQuery.data.body);
    }
  }, [draftQuery.data]);

  async function onSend() {
    setSending(true);
    setNotice(null);
    try {
      await apiPost<SentMessage>(`/todos/${todoId}/send`, { subject, body });
      await qc.invalidateQueries({ queryKey: ["todos"] });
      await qc.invalidateQueries({ queryKey: ["todo", todoId] });
      setNotice({ kind: "success", message: "Email sent." });
    } catch (err) {
      setNotice({
        kind: "error",
        message: err instanceof ApiError ? err.message : "Send failed.",
      });
    } finally {
      setSending(false);
    }
  }

  async function onSaveToMailbox() {
    setSavingToMailbox(true);
    setNotice(null);
    try {
      const result = await apiPost<SaveToMailboxResponse>(
        `/todos/${todoId}/save-to-mailbox`,
        { subject, body },
      );
      await qc.invalidateQueries({ queryKey: ["todos"] });
      await qc.invalidateQueries({ queryKey: ["todo", todoId] });
      const replaced = result.replaced_previous ? " (replaced previous)" : "";
      setNotice({
        kind: "success",
        message: `Saved to ${result.mailbox.folder}${replaced}. Finish sending from your mail client.`,
      });
    } catch (err) {
      setNotice({
        kind: "error",
        message: err instanceof ApiError ? err.message : "Save-to-mailbox failed.",
      });
    } finally {
      setSavingToMailbox(false);
    }
  }

  async function onDiscard() {
    if (!todoQuery.data) return;
    try {
      await apiDelete(`/contacts/${todoQuery.data.contact_id}/draft`);
      await qc.invalidateQueries({ queryKey: ["todos"] });
      router.push("/auth/todos");
    } catch (err) {
      setNotice({
        kind: "error",
        message: err instanceof ApiError ? err.message : "Could not discard.",
      });
    }
  }

  if (todoQuery.isLoading) return <p>Loading…</p>;
  if (todoQuery.isError || !todoQuery.data) {
    return <p className="text-destructive">Todo not found.</p>;
  }

  const todo = todoQuery.data;
  const isSend = todo.type === "send";
  const imapConfigured =
    !!settingsQuery.data?.imap.host &&
    settingsQuery.data.imap.username_set &&
    settingsQuery.data.imap.password_set;
  const busy = sending || savingToMailbox;
  const completionLabel =
    todo.status === "done"
      ? todo.completed_via === "mailbox_stored"
        ? "Completed (saved to mailbox)"
        : todo.completed_via === "sent"
          ? "Completed (sent)"
          : `Completed (${todo.completed_via ?? "manual"})`
      : null;

  return (
    <div className="max-w-3xl space-y-6">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-semibold">{todo.title}</h1>
        <Badge variant={isSend ? "default" : "secondary"}>{todo.type}</Badge>
        <Badge variant="outline">{todo.status}</Badge>
        {completionLabel && <Badge variant="secondary">{completionLabel}</Badge>}
      </div>
      {contactQuery.data && orgQuery.data && (
        <p className="text-sm text-muted-foreground">
          To: {contactQuery.data.first_name} {contactQuery.data.last_name} · {orgQuery.data.name}
          {contactQuery.data.email && (
            <> · <span className="font-mono">{contactQuery.data.email}</span></>
          )}
        </p>
      )}

      {isSend && (
        <Card>
          <CardHeader>
            <CardTitle>Compose</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {draftQuery.data === null && (
              <p className="text-sm text-destructive">
                No draft on this contact — regenerate a draft first.
              </p>
            )}
            <div className="space-y-2">
              <Label htmlFor="subject">Subject</Label>
              <Input
                id="subject"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="body">Body</Label>
              <Textarea
                id="body"
                rows={20}
                value={body}
                onChange={(e) => setBody(e.target.value)}
              />
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
            <div className="flex flex-wrap gap-3">
              <Button
                onClick={onSend}
                disabled={busy || !subject || !body || todo.status !== "open"}
              >
                {sending ? "Sending…" : "Send now"}
              </Button>
              {imapConfigured && (
                <Button
                  onClick={onSaveToMailbox}
                  disabled={busy || !subject || !body || todo.status !== "open"}
                  title="Upload the draft to your mail account's Drafts folder — you finish sending from your mail client."
                >
                  {savingToMailbox ? "Saving…" : "Save to mailbox"}
                </Button>
              )}
              <Button variant="outline" onClick={onDiscard} disabled={busy}>
                Discard draft
              </Button>
            </div>
            {!imapConfigured && (
              <p className="text-xs text-muted-foreground">
                Tip: configure IMAP in Settings to enable “Save to mailbox” — the draft lands
                in your mail client's Drafts folder for hand-editing before you send it.
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {!isSend && (
        <Card>
          <CardHeader>
            <CardTitle>Manual todo</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Non-send todos are informational for now — mark them done from the underlying
              contact once you have taken action.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
