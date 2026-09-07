"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { apiGet, apiPatch, apiPost, ApiError } from "@/lib/api";
import type { Contact, Draft, Organisation, Template } from "@/lib/types";

interface Notice {
  kind: "success" | "error";
  message: string;
}

export default function ContactDetailPage() {
  const params = useParams<{ contactId: string }>();
  const contactId = Number(params.contactId);
  const qc = useQueryClient();

  const contactQuery = useQuery({
    queryKey: ["contact", contactId],
    queryFn: () => apiGet<Contact>(`/contacts/${contactId}`),
    enabled: !Number.isNaN(contactId),
  });

  const orgQuery = useQuery({
    queryKey: ["organisation", contactQuery.data?.organisation_id],
    queryFn: () => apiGet<Organisation>(`/organisations/${contactQuery.data!.organisation_id}`),
    enabled: !!contactQuery.data,
  });

  const templatesQuery = useQuery({
    queryKey: ["templates"],
    queryFn: () => apiGet<Template[]>("/templates"),
  });

  const [templateId, setTemplateId] = useState<number | "">("");
  const [enriching, setEnriching] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);

  // Inline email editor (FR-006a) — always usable regardless of contact status or whether
  // enrichment has run. The field is dirty when the local draft differs from the value on
  // the server; Save PATCHes and re-fetches.
  const [emailDraft, setEmailDraft] = useState("");
  const [savingEmail, setSavingEmail] = useState(false);
  useEffect(() => {
    if (contactQuery.data) setEmailDraft(contactQuery.data.email ?? "");
  }, [contactQuery.data]);

  async function onSaveEmail() {
    setSavingEmail(true);
    setNotice(null);
    try {
      // Empty string is treated as "clear" — the backend PATCH accepts email: null.
      await apiPatch<Contact>(`/contacts/${contactId}`, {
        email: emailDraft.trim() || null,
      });
      await qc.invalidateQueries({ queryKey: ["contact", contactId] });
      setNotice({ kind: "success", message: "Email updated." });
    } catch (err) {
      setNotice({
        kind: "error",
        message: err instanceof ApiError ? err.message : "Could not save email.",
      });
    } finally {
      setSavingEmail(false);
    }
  }

  // Company context (FR-001a) — the org's notes are editable here so the operator can
  // capture research about the company at the moment they're drafting outreach, without
  // navigating to the Organisation page.
  const [notesDraft, setNotesDraft] = useState("");
  const [savingNotes, setSavingNotes] = useState(false);
  useEffect(() => {
    if (orgQuery.data) setNotesDraft(orgQuery.data.notes);
  }, [orgQuery.data]);

  async function onSaveNotes() {
    if (!orgQuery.data) return;
    setSavingNotes(true);
    setNotice(null);
    try {
      await apiPatch<Organisation>(`/organisations/${orgQuery.data.id}`, {
        notes: notesDraft,
      });
      await qc.invalidateQueries({
        queryKey: ["organisation", orgQuery.data.id],
      });
      await qc.invalidateQueries({ queryKey: ["organisations"] });
      setNotice({ kind: "success", message: "Company context saved." });
    } catch (err) {
      setNotice({
        kind: "error",
        message: err instanceof ApiError ? err.message : "Could not save company context.",
      });
    } finally {
      setSavingNotes(false);
    }
  }

  const draftQuery = useQuery({
    queryKey: ["draft", contactId],
    queryFn: async () => {
      try {
        return await apiGet<Draft>(`/contacts/${contactId}/draft`);
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) return null;
        throw err;
      }
    },
    enabled: !Number.isNaN(contactId),
  });

  async function onEnrich() {
    setEnriching(true);
    setNotice(null);
    try {
      await apiPost<Contact>(`/contacts/${contactId}/enrich`);
      await qc.invalidateQueries({ queryKey: ["contact", contactId] });
      await qc.invalidateQueries({ queryKey: ["organisation"] });
      setNotice({ kind: "success", message: "Contact enriched." });
    } catch (err) {
      setNotice({
        kind: "error",
        message: err instanceof ApiError ? err.message : "Enrichment failed.",
      });
    } finally {
      setEnriching(false);
    }
  }

  async function onGenerate() {
    if (!templateId) {
      setNotice({ kind: "error", message: "Pick a template first." });
      return;
    }
    setGenerating(true);
    setNotice(null);
    try {
      await apiPost<Draft>(`/contacts/${contactId}/drafts`, { template_id: templateId });
      await qc.invalidateQueries({ queryKey: ["draft", contactId] });
      await qc.invalidateQueries({ queryKey: ["contact", contactId] });
      setNotice({ kind: "success", message: "Draft generated." });
    } catch (err) {
      setNotice({
        kind: "error",
        message: err instanceof ApiError ? err.message : "Generation failed.",
      });
    } finally {
      setGenerating(false);
    }
  }

  if (contactQuery.isLoading) return <p>Loading…</p>;
  if (contactQuery.isError || !contactQuery.data) {
    return <p className="text-destructive">Could not load contact.</p>;
  }

  const contact = contactQuery.data;
  const org = orgQuery.data;
  const draft = draftQuery.data;

  return (
    <div className="max-w-3xl space-y-6">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-semibold">
          {contact.first_name} {contact.last_name}
        </h1>
        <Badge variant="secondary">{contact.status}</Badge>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Contact</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div>
            <span className="text-muted-foreground">Organisation:</span> {org?.name ?? "…"}
            {org?.domain && <span className="text-muted-foreground"> · {org.domain}</span>}
          </div>
          <div className="space-y-1">
            <Label htmlFor="contact-email" className="text-xs text-muted-foreground">
              Email (editable — hand corrections survive re-enrichment)
            </Label>
            <div className="flex gap-2">
              <Input
                id="contact-email"
                type="email"
                value={emailDraft}
                onChange={(e) => setEmailDraft(e.target.value)}
                placeholder="name@company.com"
              />
              <Button
                type="button"
                variant="outline"
                onClick={onSaveEmail}
                disabled={savingEmail || (emailDraft.trim() || null) === (contact.email ?? null)}
              >
                {savingEmail ? "Saving…" : "Save email"}
              </Button>
            </div>
          </div>
          <div>
            <span className="text-muted-foreground">Position:</span> {contact.position ?? "—"}
          </div>
          {contact.last_enrichment_error && (
            <p className="text-destructive">
              Last enrichment error: {contact.last_enrichment_error}
            </p>
          )}
          {contact.last_generation_error && (
            <p className="text-destructive">
              Last generation error: {contact.last_generation_error}
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Company context</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Label htmlFor="org-notes" className="text-xs text-muted-foreground">
            Research notes on {org?.name ?? "the organisation"} — visible on the Organisation
            page and used purely as context for you (not sent to the LLM).
          </Label>
          <Textarea
            id="org-notes"
            rows={6}
            value={notesDraft}
            onChange={(e) => setNotesDraft(e.target.value)}
            placeholder="e.g. just raised Series B, CEO on podcast last week, hiring 5 engineers…"
            disabled={!orgQuery.data}
          />
          <Button
            type="button"
            variant="outline"
            onClick={onSaveNotes}
            disabled={
              savingNotes ||
              !orgQuery.data ||
              notesDraft === (orgQuery.data?.notes ?? "")
            }
          >
            {savingNotes ? "Saving…" : "Save context"}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Actions</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-3">
            <Button onClick={onEnrich} disabled={enriching}>
              {enriching ? "Enriching…" : "Enrich (Hunter)"}
            </Button>
            <div className="flex items-center gap-2">
              <select
                className="h-10 rounded-md border border-input bg-background px-3 py-2 text-sm"
                value={templateId}
                onChange={(e) => setTemplateId(e.target.value ? Number(e.target.value) : "")}
              >
                <option value="">Pick a template…</option>
                {(templatesQuery.data ?? []).map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
              <Button onClick={onGenerate} disabled={generating || !templateId}>
                {generating ? "Generating…" : "Generate draft"}
              </Button>
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
        </CardContent>
      </Card>

      {draft && (
        <Card>
          <CardHeader>
            <CardTitle>Draft</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="text-sm">
              <span className="text-muted-foreground">Subject:</span>{" "}
              <span className="font-medium">{draft.subject}</span>
            </div>
            <pre className="whitespace-pre-wrap rounded-md border bg-muted/40 p-4 text-sm">
              {draft.body}
            </pre>
            <p className="text-xs text-muted-foreground">
              Generated {new Date(draft.generated_at).toLocaleString()} — a Send todo has been
              opened.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
