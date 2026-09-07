"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiGet, apiPatch, apiPost, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { Contact, Gender, Organisation, Paginated } from "@/lib/types";

type Mode = "new" | "existing";

interface DomainLookupOut {
  domain: string | null;
  confidence: number | null;
  source: "hunter";
  message: string | null;
}

export default function LeadsPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("new");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ---- New-lead form ------------------------------------------------------
  const [orgName, setOrgName] = useState("");
  const [orgDomain, setOrgDomain] = useState("");
  const [selectedOrgId, setSelectedOrgId] = useState<number | null>(null);
  const [selectedOrgOriginalDomain, setSelectedOrgOriginalDomain] = useState<string | null>(null);
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [gender, setGender] = useState<Gender | "">("");
  const [manualEmail, setManualEmail] = useState("");
  const [lookupPending, setLookupPending] = useState(false);
  const [lookupHint, setLookupHint] = useState<string | null>(null);

  // FR-004b / FR-004d: contact-name, salutation, and manual-email fields are gated
  // behind a non-empty domain. Either Hunter fills it (via the explicit "Look up
  // domain" click below) or the operator types it in by hand.
  const gateOpen = orgDomain.trim().length > 0;

  function onOrgNameChange(v: string) {
    setOrgName(v);
    if (selectedOrgId !== null) {
      // Editing the company name means the operator is no longer reusing the
      // pre-selected organisation — drop the reuse binding.
      setSelectedOrgId(null);
      setSelectedOrgOriginalDomain(null);
    }
    setLookupHint(null);
  }

  async function onLookupDomain() {
    if (!orgName.trim()) return;
    setLookupHint(null);
    setError(null);
    setLookupPending(true);
    try {
      const out = await apiPost<DomainLookupOut>("/hunter/domain-lookup", {
        company_name: orgName,
      });
      if (out.domain) {
        setOrgDomain(out.domain);
      } else {
        setOrgDomain("");
        setLookupHint(out.message ?? "No domain found. Enter it manually to continue.");
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Domain lookup failed.");
    } finally {
      setLookupPending(false);
    }
  }

  // ---- Existing-organisation autocomplete (FR-004c) -----------------------
  const orgSuggestParams = new URLSearchParams({ limit: "5", q: orgName.trim() });
  const orgSuggestQuery = useQuery({
    queryKey: ["lead-org-suggest", orgName.trim()],
    queryFn: () =>
      apiGet<Paginated<Organisation>>(`/organisations?${orgSuggestParams.toString()}`),
    enabled: mode === "new" && orgName.trim().length >= 2 && selectedOrgId === null,
  });

  function pickExistingOrg(org: Organisation) {
    // FR-004c: reusing an existing organisation pre-fills the domain and unlocks the
    // gated fields immediately — no Hunter Domain lookup is issued.
    setSelectedOrgId(org.id);
    setSelectedOrgOriginalDomain(org.domain ?? null);
    setOrgName(org.name);
    setOrgDomain(org.domain ?? "");
    setLookupHint(null);
    setError(null);
  }

  async function onCreateNew(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setPending(true);
    try {
      let organisationId: number;
      if (selectedOrgId !== null) {
        organisationId = selectedOrgId;
        // If the operator typed a domain onto an existing org that had none (or
        // edited the shown value), persist the change so the org gets the benefit.
        if (orgDomain && orgDomain !== (selectedOrgOriginalDomain ?? "")) {
          await apiPatch<Organisation>(`/organisations/${selectedOrgId}`, {
            domain: orgDomain,
          });
        }
      } else {
        const org = await apiPost<Organisation>("/organisations", {
          name: orgName,
          domain: orgDomain || null,
        });
        organisationId = org.id;
      }
      const contact = await apiPost<Contact>("/contacts", {
        organisation_id: organisationId,
        first_name: firstName,
        last_name: lastName,
        gender: gender || null,
        email: manualEmail.trim() || null,
      });
      router.push(`/auth/leads/${contact.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create lead.");
    } finally {
      setPending(false);
    }
  }

  // ---- Existing-contact picker (mode='existing') --------------------------
  // FR-027b: this picker is a *workflow* affordance for reusing a contact — delete is
  // intentionally not exposed here so operators can't accidentally destroy records
  // from a "start a new lead" context. Delete lives on the Contact detail and the
  // Contacts list only.
  const [contactSearch, setContactSearch] = useState("");
  const contactQueryParams = new URLSearchParams({ limit: "20" });
  if (contactSearch) contactQueryParams.set("q", contactSearch);
  const contactSearchQuery = useQuery({
    queryKey: ["lead-contact-search", contactSearch],
    queryFn: () =>
      apiGet<Paginated<Contact>>(`/contacts?${contactQueryParams.toString()}`),
    enabled: mode === "existing",
  });

  return (
    <div className="max-w-xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">New lead</h1>
        <p className="text-sm text-muted-foreground">
          Add a company and a contact, or pick someone already in the database.
        </p>
      </div>

      <div className="inline-flex rounded-md border p-1">
        {(["new", "existing"] as Mode[]).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => setMode(m)}
            className={cn(
              "rounded-md px-3 py-1 text-sm",
              mode === m ? "bg-primary text-primary-foreground" : "hover:bg-muted",
            )}
          >
            {m === "new" ? "New contact" : "Existing contact"}
          </button>
        ))}
      </div>

      {mode === "new" && (
        <Card>
          <CardHeader>
            <CardTitle>Organisation + contact</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={onCreateNew} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="org-name">Company name</Label>
                <div className="flex gap-2">
                  <Input
                    id="org-name"
                    value={orgName}
                    onChange={(e) => onOrgNameChange(e.target.value)}
                    required
                  />
                  <Button
                    type="button"
                    onClick={onLookupDomain}
                    disabled={
                      !orgName.trim() || lookupPending || selectedOrgId !== null
                    }
                  >
                    {lookupPending ? "Looking…" : "Look up domain"}
                  </Button>
                </div>
                {selectedOrgId !== null && (
                  <p className="text-xs text-muted-foreground">
                    Reusing an existing organisation from the database.
                  </p>
                )}
                {orgSuggestQuery.data && orgSuggestQuery.data.items.length > 0 && (
                  <div
                    role="listbox"
                    aria-label="Existing organisations"
                    className="divide-y rounded border bg-popover"
                  >
                    <p className="px-3 py-1 text-xs text-muted-foreground">
                      Match in database:
                    </p>
                    {orgSuggestQuery.data.items.map((org) => (
                      <button
                        key={org.id}
                        type="button"
                        role="option"
                        aria-selected="false"
                        onClick={() => pickExistingOrg(org)}
                        className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-muted/50"
                      >
                        <span className="font-medium">{org.name}</span>
                        {org.domain && (
                          <span className="font-mono text-xs text-muted-foreground">
                            {org.domain}
                          </span>
                        )}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <div className="space-y-2">
                <Label htmlFor="org-domain">Domain</Label>
                <Input
                  id="org-domain"
                  placeholder="acme.com"
                  value={orgDomain}
                  onChange={(e) => {
                    setOrgDomain(e.target.value);
                    setLookupHint(null);
                  }}
                />
                {lookupHint && (
                  <p className="text-xs text-muted-foreground">{lookupHint}</p>
                )}
                {!gateOpen && !lookupHint && (
                  <p className="text-xs text-muted-foreground">
                    Look up the domain from the company name, or type it in, to unlock
                    the contact fields.
                  </p>
                )}
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="first-name">First name</Label>
                  <Input
                    id="first-name"
                    value={firstName}
                    onChange={(e) => setFirstName(e.target.value)}
                    disabled={!gateOpen}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="last-name">Last name</Label>
                  <Input
                    id="last-name"
                    value={lastName}
                    onChange={(e) => setLastName(e.target.value)}
                    disabled={!gateOpen}
                    required
                  />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="gender">Salutation</Label>
                <select
                  id="gender"
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-50"
                  value={gender}
                  disabled={!gateOpen}
                  onChange={(e) => setGender(e.target.value as Gender | "")}
                >
                  <option value="">(unspecified)</option>
                  <option value="m">Male</option>
                  <option value="f">Female</option>
                  <option value="d">Diverse</option>
                </select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="manual-email">Email (optional)</Label>
                <Input
                  id="manual-email"
                  type="email"
                  value={manualEmail}
                  placeholder="max@acme.com"
                  disabled={!gateOpen}
                  onChange={(e) => setManualEmail(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  Skip to let Enrich fill it via Hunter — or type it manually now.
                </p>
              </div>

              {error && <p className="text-sm text-destructive">{error}</p>}
              <Button type="submit" disabled={pending || !gateOpen}>
                {pending ? "Creating…" : "Create lead"}
              </Button>
            </form>
          </CardContent>
        </Card>
      )}

      {mode === "existing" && (
        <Card>
          <CardHeader>
            <CardTitle>Pick an existing contact</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <Input
              placeholder="Search by name or email…"
              value={contactSearch}
              onChange={(e) => setContactSearch(e.target.value)}
              autoFocus
            />
            {contactSearchQuery.isLoading && (
              <p className="text-sm text-muted-foreground">Searching…</p>
            )}
            <div className="max-h-80 overflow-y-auto">
              {(contactSearchQuery.data?.items ?? []).map((c) => (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => router.push(`/auth/leads/${c.id}`)}
                  className="flex w-full items-center justify-between rounded border-b px-3 py-2 text-left hover:bg-muted/50"
                >
                  <div>
                    <div className="font-medium">
                      {c.first_name} {c.last_name}
                    </div>
                    {c.email && (
                      <div className="font-mono text-xs text-muted-foreground">
                        {c.email}
                      </div>
                    )}
                  </div>
                  <span className="text-xs text-muted-foreground">{c.status}</span>
                </button>
              ))}
              {contactSearchQuery.data?.items.length === 0 && (
                <p className="px-3 py-2 text-sm text-muted-foreground">No matches.</p>
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
