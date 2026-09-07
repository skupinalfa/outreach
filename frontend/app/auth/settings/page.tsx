"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiGet, apiPatch, apiPost, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type {
  ImapTestConnectionResult,
  SettingsView,
  TestConnectionResult,
} from "@/lib/types";

interface Draft {
  hunter_api_key: string;
  openai_api_key: string;
  smtp_host: string;
  smtp_port: string;
  smtp_username: string;
  smtp_password: string;
  imap_host: string;
  imap_port: string;
  imap_username: string;
  imap_password: string;
  imap_use_tls: boolean;
  imap_drafts_folder: string;
  sender_display_name: string;
  sender_email: string;
  follow_up_cadence_days: string;
  openai_model: string;
  timezone: string;
}

const EMPTY_DRAFT: Draft = {
  hunter_api_key: "",
  openai_api_key: "",
  smtp_host: "",
  smtp_port: "",
  smtp_username: "",
  smtp_password: "",
  imap_host: "",
  imap_port: "",
  imap_username: "",
  imap_password: "",
  imap_use_tls: true,
  imap_drafts_folder: "",
  sender_display_name: "",
  sender_email: "",
  follow_up_cadence_days: "",
  openai_model: "",
  timezone: "",
};

type Section = "hunter" | "openai" | "smtp" | "imap";

interface Notice {
  section: string;
  kind: "success" | "error";
  message: string;
}

export default function SettingsPage() {
  const qc = useQueryClient();
  const searchParams = useSearchParams();
  const highlight = searchParams.get("highlight") as Section | null;

  const settingsQuery = useQuery({
    queryKey: ["settings"],
    queryFn: () => apiGet<SettingsView>("/settings"),
  });

  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT);
  const [notices, setNotices] = useState<Notice[]>([]);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState<Section | null>(null);

  useEffect(() => {
    if (!settingsQuery.data) return;
    const s = settingsQuery.data;
    setDraft({
      hunter_api_key: "",
      openai_api_key: "",
      smtp_host: s.smtp.host ?? "",
      smtp_port: s.smtp.port ? String(s.smtp.port) : "",
      smtp_username: "",
      smtp_password: "",
      imap_host: s.imap.host ?? "",
      imap_port: s.imap.port ? String(s.imap.port) : "",
      imap_username: "",
      imap_password: "",
      imap_use_tls: s.imap.use_tls,
      imap_drafts_folder: s.imap.drafts_folder ?? "",
      sender_display_name: s.sender_display_name ?? "",
      sender_email: s.sender_email ?? "",
      follow_up_cadence_days: String(s.follow_up_cadence_days),
      openai_model: s.openai_model,
      timezone: s.timezone,
    });
  }, [settingsQuery.data]);

  const highlightRing = useMemo(
    () => (section: Section) =>
      highlight === section ? "ring-2 ring-primary shadow-md" : undefined,
    [highlight],
  );

  function pushNotice(n: Notice) {
    setNotices((prev) => [...prev.filter((p) => p.section !== n.section), n]);
  }

  async function onSaveAll() {
    setSaving(true);
    setNotices([]);
    try {
      // Only send fields the operator actually filled in. Sending `""` for an untouched
      // field would either wipe the stored value or (for EmailStr) 422 the whole request
      // and drop the useful fields with it.
      const patch: Record<string, unknown> = {};
      if (draft.hunter_api_key) patch.hunter_api_key = draft.hunter_api_key;
      if (draft.openai_api_key) patch.openai_api_key = draft.openai_api_key;

      const smtp: Record<string, unknown> = {};
      if (draft.smtp_host) smtp.host = draft.smtp_host;
      if (draft.smtp_port) smtp.port = Number(draft.smtp_port);
      if (draft.smtp_username) smtp.username = draft.smtp_username;
      if (draft.smtp_password) smtp.password = draft.smtp_password;
      if (Object.keys(smtp).length > 0) patch.smtp = smtp;

      const imap: Record<string, unknown> = {};
      if (draft.imap_host) imap.host = draft.imap_host;
      if (draft.imap_port) imap.port = Number(draft.imap_port);
      if (draft.imap_username) imap.username = draft.imap_username;
      if (draft.imap_password) imap.password = draft.imap_password;
      if (s.imap.use_tls !== draft.imap_use_tls) imap.use_tls = draft.imap_use_tls;
      if (draft.imap_drafts_folder !== (s.imap.drafts_folder ?? "")) {
        imap.drafts_folder = draft.imap_drafts_folder;
      }
      if (Object.keys(imap).length > 0) patch.imap = imap;

      if (draft.sender_display_name) patch.sender_display_name = draft.sender_display_name;
      if (draft.sender_email) patch.sender_email = draft.sender_email;
      if (draft.follow_up_cadence_days) {
        patch.follow_up_cadence_days = Number(draft.follow_up_cadence_days);
      }
      if (draft.openai_model) patch.openai_model = draft.openai_model;
      if (draft.timezone) patch.timezone = draft.timezone;

      await apiPatch<SettingsView>("/settings", patch);
      await qc.invalidateQueries({ queryKey: ["settings"] });
      pushNotice({ section: "save", kind: "success", message: "Settings saved." });
    } catch (err) {
      pushNotice({
        section: "save",
        kind: "error",
        message: err instanceof ApiError ? err.message : "Save failed.",
      });
    } finally {
      setSaving(false);
    }
  }

  async function onTest(section: Section) {
    setTesting(section);
    try {
      let payload: Record<string, unknown> = {};
      const path = `/settings/test/${section}`;
      if (section === "hunter") {
        payload = draft.hunter_api_key ? { api_key: draft.hunter_api_key } : {};
      } else if (section === "openai") {
        payload = draft.openai_api_key ? { api_key: draft.openai_api_key } : {};
      } else if (section === "smtp") {
        payload = {};
        if (draft.smtp_host) payload.host = draft.smtp_host;
        if (draft.smtp_port) payload.port = Number(draft.smtp_port);
        if (draft.smtp_username) payload.username = draft.smtp_username;
        if (draft.smtp_password) payload.password = draft.smtp_password;
      } else {
        payload = {};
        if (draft.imap_host) payload.host = draft.imap_host;
        if (draft.imap_port) payload.port = Number(draft.imap_port);
        if (draft.imap_username) payload.username = draft.imap_username;
        if (draft.imap_password) payload.password = draft.imap_password;
        payload.use_tls = draft.imap_use_tls;
      }
      const result =
        section === "imap"
          ? await apiPost<ImapTestConnectionResult>(path, payload)
          : await apiPost<TestConnectionResult>(path, payload);
      const message =
        section === "imap" && result.ok && (result as ImapTestConnectionResult).resolved_drafts_folder
          ? `${result.message}`
          : result.message;
      pushNotice({
        section,
        kind: result.ok ? "success" : "error",
        message,
      });
    } catch (err) {
      pushNotice({
        section,
        kind: "error",
        message: err instanceof ApiError ? err.message : "Test failed.",
      });
    } finally {
      setTesting(null);
    }
  }

  if (settingsQuery.isLoading) return <p>Loading…</p>;
  if (settingsQuery.isError || !settingsQuery.data) {
    return <p className="text-destructive">Could not load settings.</p>;
  }

  const s = settingsQuery.data;

  function noticeFor(section: string) {
    const n = notices.find((x) => x.section === section);
    if (!n) return null;
    return (
      <p
        className={n.kind === "error" ? "text-sm text-destructive" : "text-sm text-emerald-600"}
      >
        {n.message}
      </p>
    );
  }

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Credentials are encrypted at rest. Leaving a field blank keeps the stored value.
        </p>
      </div>

      <Card className={cn(highlightRing("hunter"))}>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            Enrichment (Hunter)
            {s.hunter_api_key_set ? (
              <Badge variant="secondary">•••••• (set)</Badge>
            ) : (
              <Badge variant="destructive">not set</Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-2">
            <Label htmlFor="hunter-key">Hunter API key</Label>
            <Input
              id="hunter-key"
              type="password"
              value={draft.hunter_api_key}
              onChange={(e) => setDraft({ ...draft, hunter_api_key: e.target.value })}
              placeholder={s.hunter_api_key_set ? "Leave blank to keep current" : "Paste new key"}
            />
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              type="button"
              disabled={testing !== null}
              onClick={() => onTest("hunter")}
            >
              {testing === "hunter" ? "Testing…" : "Test connection"}
            </Button>
          </div>
          {noticeFor("hunter")}
        </CardContent>
      </Card>

      <Card className={cn(highlightRing("openai"))}>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            LLM (OpenAI)
            {s.openai_api_key_set ? (
              <Badge variant="secondary">•••••• (set)</Badge>
            ) : (
              <Badge variant="destructive">not set</Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-2">
            <Label htmlFor="openai-key">OpenAI API key</Label>
            <Input
              id="openai-key"
              type="password"
              value={draft.openai_api_key}
              onChange={(e) => setDraft({ ...draft, openai_api_key: e.target.value })}
              placeholder={s.openai_api_key_set ? "Leave blank to keep current" : "sk-…"}
            />
          </div>
          <Button
            variant="outline"
            type="button"
            disabled={testing !== null}
            onClick={() => onTest("openai")}
          >
            {testing === "openai" ? "Testing…" : "Test connection"}
          </Button>
          {noticeFor("openai")}
        </CardContent>
      </Card>

      <Card className={cn(highlightRing("smtp"))}>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            Outbound mail (SMTP)
            {s.smtp.username_set && s.smtp.password_set ? (
              <Badge variant="secondary">credentials set</Badge>
            ) : (
              <Badge variant="destructive">incomplete</Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-3 gap-3">
            <div className="col-span-2 space-y-2">
              <Label htmlFor="smtp-host">Host</Label>
              <Input
                id="smtp-host"
                value={draft.smtp_host}
                onChange={(e) => setDraft({ ...draft, smtp_host: e.target.value })}
                placeholder="smtp.mailbox.org"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="smtp-port">Port</Label>
              <Input
                id="smtp-port"
                inputMode="numeric"
                value={draft.smtp_port}
                onChange={(e) => setDraft({ ...draft, smtp_port: e.target.value })}
                placeholder="465"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="smtp-username">Username</Label>
              <Input
                id="smtp-username"
                value={draft.smtp_username}
                onChange={(e) => setDraft({ ...draft, smtp_username: e.target.value })}
                placeholder={s.smtp.username_set ? "Leave blank to keep current" : "user@…"}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="smtp-password">Password</Label>
              <Input
                id="smtp-password"
                type="password"
                value={draft.smtp_password}
                onChange={(e) => setDraft({ ...draft, smtp_password: e.target.value })}
                placeholder={s.smtp.password_set ? "Leave blank to keep current" : ""}
              />
            </div>
          </div>
          <Button
            variant="outline"
            type="button"
            disabled={testing !== null}
            onClick={() => onTest("smtp")}
          >
            {testing === "smtp" ? "Testing…" : "Test connection"}
          </Button>
          {noticeFor("smtp")}
        </CardContent>
      </Card>

      <Card className={cn(highlightRing("imap"))}>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            Save-to-mailbox (IMAP)
            {s.imap.host && s.imap.username_set && s.imap.password_set ? (
              <Badge variant="secondary">
                {s.imap.drafts_folder_detected
                  ? `credentials set · Drafts: ${s.imap.drafts_folder_detected}`
                  : "credentials set"}
              </Badge>
            ) : (
              <Badge variant="destructive">not configured</Badge>
            )}
          </CardTitle>
          <p className="text-sm text-muted-foreground">
            Optional. When configured, the todo screen shows a “Save to mailbox” button that
            uploads the draft to your mail account instead of sending directly.
          </p>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-3 gap-3">
            <div className="col-span-2 space-y-2">
              <Label htmlFor="imap-host">Host</Label>
              <Input
                id="imap-host"
                value={draft.imap_host}
                onChange={(e) => setDraft({ ...draft, imap_host: e.target.value })}
                placeholder="imap.mailbox.org"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="imap-port">Port</Label>
              <Input
                id="imap-port"
                inputMode="numeric"
                value={draft.imap_port}
                onChange={(e) => setDraft({ ...draft, imap_port: e.target.value })}
                placeholder="993"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="imap-username">Username</Label>
              <Input
                id="imap-username"
                value={draft.imap_username}
                onChange={(e) => setDraft({ ...draft, imap_username: e.target.value })}
                placeholder={s.imap.username_set ? "Leave blank to keep current" : "user@…"}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="imap-password">Password / app-password</Label>
              <Input
                id="imap-password"
                type="password"
                value={draft.imap_password}
                onChange={(e) => setDraft({ ...draft, imap_password: e.target.value })}
                placeholder={s.imap.password_set ? "Leave blank to keep current" : ""}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={draft.imap_use_tls}
                onChange={(e) => setDraft({ ...draft, imap_use_tls: e.target.checked })}
              />
              Use TLS (port 993). Uncheck for STARTTLS (usually port 143).
            </label>
            <div className="space-y-2">
              <Label htmlFor="imap-drafts-folder">
                Drafts folder override (optional)
              </Label>
              <Input
                id="imap-drafts-folder"
                value={draft.imap_drafts_folder}
                onChange={(e) =>
                  setDraft({ ...draft, imap_drafts_folder: e.target.value })
                }
                placeholder="Auto-detected"
              />
            </div>
          </div>
          <Button
            variant="outline"
            type="button"
            disabled={testing !== null}
            onClick={() => onTest("imap")}
          >
            {testing === "imap" ? "Testing…" : "Test connection"}
          </Button>
          {noticeFor("imap")}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Preferences</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="sender-name">Sender display name</Label>
              <Input
                id="sender-name"
                value={draft.sender_display_name}
                onChange={(e) => setDraft({ ...draft, sender_display_name: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="sender-email">Sender email</Label>
              <Input
                id="sender-email"
                type="email"
                value={draft.sender_email}
                onChange={(e) => setDraft({ ...draft, sender_email: e.target.value })}
              />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-2">
              <Label htmlFor="cadence">Follow-up cadence (business days)</Label>
              <Input
                id="cadence"
                inputMode="numeric"
                value={draft.follow_up_cadence_days}
                onChange={(e) =>
                  setDraft({ ...draft, follow_up_cadence_days: e.target.value })
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="model">OpenAI model</Label>
              <Input
                id="model"
                value={draft.openai_model}
                onChange={(e) => setDraft({ ...draft, openai_model: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="tz">Timezone (IANA)</Label>
              <Input
                id="tz"
                value={draft.timezone}
                onChange={(e) => setDraft({ ...draft, timezone: e.target.value })}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="flex items-center gap-3">
        <Button onClick={onSaveAll} disabled={saving}>
          {saving ? "Saving…" : "Save all"}
        </Button>
        {noticeFor("save")}
      </div>
    </div>
  );
}
