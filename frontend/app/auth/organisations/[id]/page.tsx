"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { InlineEmailCell } from "@/components/inline-email-cell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { apiGet, apiPatch, apiPost, ApiError } from "@/lib/api";
import type { Contact, Gender, Organisation } from "@/lib/types";

interface Notice {
  kind: "success" | "error";
  message: string;
}

export default function OrganisationDetailPage() {
  const params = useParams<{ id: string }>();
  const orgId = Number(params.id);
  const qc = useQueryClient();
  const [notice, setNotice] = useState<Notice | null>(null);

  const orgQuery = useQuery({
    queryKey: ["organisation", orgId],
    queryFn: () => apiGet<Organisation>(`/organisations/${orgId}`),
    enabled: !Number.isNaN(orgId),
  });
  const contactsQuery = useQuery({
    queryKey: ["organisation", orgId, "contacts"],
    queryFn: () => apiGet<Contact[]>(`/organisations/${orgId}/contacts`),
    enabled: !Number.isNaN(orgId),
  });

  const [name, setName] = useState("");
  const [domain, setDomain] = useState("");
  const [notes, setNotes] = useState("");

  useEffect(() => {
    if (!orgQuery.data) return;
    setName(orgQuery.data.name);
    setDomain(orgQuery.data.domain ?? "");
    setNotes(orgQuery.data.notes);
  }, [orgQuery.data]);

  const patch = useMutation({
    mutationFn: () =>
      apiPatch<Organisation>(`/organisations/${orgId}`, {
        name,
        domain: domain || null,
        notes,
      }),
    onSuccess: async () => {
      setNotice({ kind: "success", message: "Saved." });
      await qc.invalidateQueries({ queryKey: ["organisation", orgId] });
      await qc.invalidateQueries({ queryKey: ["organisations"] });
    },
    onError: (err) =>
      setNotice({
        kind: "error",
        message: err instanceof ApiError ? err.message : "Save failed.",
      }),
  });

  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [gender, setGender] = useState<Gender | "">("");
  const [email, setEmail] = useState("");
  const [position, setPosition] = useState("");

  const addContact = useMutation({
    mutationFn: () =>
      apiPost<Contact>("/contacts", {
        organisation_id: orgId,
        first_name: firstName,
        last_name: lastName,
        gender: gender || null,
        email: email || null,
        position: position || null,
      }),
    onSuccess: async () => {
      setFirstName("");
      setLastName("");
      setGender("");
      setEmail("");
      setPosition("");
      setNotice({ kind: "success", message: "Contact added." });
      await qc.invalidateQueries({ queryKey: ["organisation", orgId, "contacts"] });
    },
    onError: (err) =>
      setNotice({
        kind: "error",
        message: err instanceof ApiError ? err.message : "Could not add contact.",
      }),
  });

  if (orgQuery.isLoading) return <p>Loading…</p>;
  if (orgQuery.isError || !orgQuery.data) {
    return <p className="text-destructive">Organisation not found.</p>;
  }

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <Link href="/auth/organisations" className="text-sm text-muted-foreground hover:underline">
          ← All organisations
        </Link>
        <h1 className="mt-1 text-2xl font-semibold">{orgQuery.data.name}</h1>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Organisation details</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-2">
            <Label htmlFor="org-name">Name</Label>
            <Input id="org-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="org-domain">Domain</Label>
            <Input id="org-domain" value={domain} onChange={(e) => setDomain(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="org-notes">Notes</Label>
            <Textarea id="org-notes" rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} />
          </div>
          <Button onClick={() => patch.mutate()} disabled={patch.isPending}>
            {patch.isPending ? "Saving…" : "Save"}
          </Button>
        </CardContent>
      </Card>

      {notice && (
        <p
          className={notice.kind === "error" ? "text-sm text-destructive" : "text-sm text-emerald-600"}
        >
          {notice.message}
        </p>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Contacts ({contactsQuery.data?.length ?? 0})</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {(contactsQuery.data ?? []).map((c) => (
              <div key={c.id} className="rounded border px-3 py-2">
                <div className="flex items-center justify-between">
                  <div>
                    <Link href={`/auth/leads/${c.id}`} className="font-medium hover:underline">
                      {c.first_name} {c.last_name}
                    </Link>
                    {c.position && (
                      <span className="ml-2 text-xs text-muted-foreground">{c.position}</span>
                    )}
                  </div>
                  <Badge variant="secondary">{c.status}</Badge>
                </div>
                <div className="mt-2">
                  <InlineEmailCell
                    contactId={c.id}
                    currentEmail={c.email}
                    invalidateKeys={[
                      ["organisation", orgId, "contacts"],
                      ["contact", c.id],
                      ["contacts"],
                    ]}
                  />
                </div>
              </div>
            ))}
            {contactsQuery.data?.length === 0 && (
              <p className="text-sm text-muted-foreground">No contacts yet.</p>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Add contact</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="c-first">First name</Label>
              <Input id="c-first" value={firstName} onChange={(e) => setFirstName(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="c-last">Last name</Label>
              <Input id="c-last" value={lastName} onChange={(e) => setLastName(e.target.value)} />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-2">
              <Label htmlFor="c-gender">Salutation</Label>
              <select
                id="c-gender"
                className="h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                value={gender}
                onChange={(e) => setGender(e.target.value as Gender | "")}
              >
                <option value="">(unspecified)</option>
                <option value="m">Male</option>
                <option value="f">Female</option>
                <option value="d">Diverse</option>
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="c-email">Email</Label>
              <Input
                id="c-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="c-position">Position</Label>
              <Input
                id="c-position"
                value={position}
                onChange={(e) => setPosition(e.target.value)}
              />
            </div>
          </div>
          <Button
            onClick={() => addContact.mutate()}
            disabled={addContact.isPending || !firstName || !lastName}
          >
            {addContact.isPending ? "Adding…" : "Add contact"}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
