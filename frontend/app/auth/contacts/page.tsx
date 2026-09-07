"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { DeleteConfirmDialog } from "@/components/delete-confirm-dialog";
import { InlineEmailCell } from "@/components/inline-email-cell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiGet } from "@/lib/api";
import type { Contact, ContactStatus, Organisation, Paginated } from "@/lib/types";

const STATUSES: (ContactStatus | "")[] = [
  "",
  "new",
  "enriched",
  "contacted",
  "replied",
  "not_interested",
  "meeting_booked",
];

export default function ContactsPage() {
  const [search, setSearch] = useState("");
  const [orgId, setOrgId] = useState<string>("");
  const [status, setStatus] = useState<ContactStatus | "">("");
  const [pendingDelete, setPendingDelete] = useState<Contact | null>(null);

  const orgsQuery = useQuery({
    queryKey: ["organisations", "for-filter"],
    queryFn: () => apiGet<Paginated<Organisation>>("/organisations?limit=200"),
  });

  const params = new URLSearchParams({ limit: "100" });
  if (search) params.set("q", search);
  if (orgId) params.set("organisation_id", orgId);
  if (status) params.set("status", status);

  const contactsQuery = useQuery({
    queryKey: ["contacts", search, orgId, status],
    queryFn: () => apiGet<Paginated<Contact>>(`/contacts?${params.toString()}`),
  });

  const orgName = (id: number) =>
    orgsQuery.data?.items.find((o) => o.id === id)?.name ?? "…";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Contacts</h1>
        <p className="text-sm text-muted-foreground">
          Everyone in the database, across all organisations.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <Input
          placeholder="Search name or email…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select
          className="h-10 rounded-md border border-input bg-background px-3 py-2 text-sm"
          value={orgId}
          onChange={(e) => setOrgId(e.target.value)}
        >
          <option value="">All organisations</option>
          {(orgsQuery.data?.items ?? []).map((o) => (
            <option key={o.id} value={o.id}>
              {o.name}
            </option>
          ))}
        </select>
        <select
          className="h-10 rounded-md border border-input bg-background px-3 py-2 text-sm"
          value={status}
          onChange={(e) => setStatus(e.target.value as ContactStatus | "")}
        >
          {STATUSES.map((s) => (
            <option key={s || "any"} value={s}>
              {s ? s : "All statuses"}
            </option>
          ))}
        </select>
      </div>

      <DeleteConfirmDialog
        open={pendingDelete !== null}
        impactPath={`/contacts/${pendingDelete?.id ?? 0}/delete-impact`}
        deletePath={`/contacts/${pendingDelete?.id ?? 0}`}
        entityKind="contact"
        entityName={
          pendingDelete ? `${pendingDelete.first_name} ${pendingDelete.last_name}`.trim() : ""
        }
        onClose={() => setPendingDelete(null)}
        invalidateQueryKeys={[["contacts"], ["organisations"]]}
      />

      <div className="rounded-md border">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-left">
            <tr>
              <th className="px-4 py-2 font-medium">Name</th>
              <th className="px-4 py-2 font-medium">Organisation</th>
              <th className="px-4 py-2 font-medium">Email</th>
              <th className="px-4 py-2 font-medium">Status</th>
              <th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody>
            {contactsQuery.isLoading && (
              <tr>
                <td colSpan={5} className="px-4 py-4 text-muted-foreground">
                  Loading…
                </td>
              </tr>
            )}
            {contactsQuery.data?.items.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-4 text-muted-foreground">
                  No contacts found.
                </td>
              </tr>
            )}
            {(contactsQuery.data?.items ?? []).map((c) => (
              <tr key={c.id} className="border-t">
                <td className="px-4 py-2">
                  <Link href={`/auth/leads/${c.id}`} className="font-medium hover:underline">
                    {c.first_name} {c.last_name}
                  </Link>
                </td>
                <td className="px-4 py-2 text-muted-foreground">
                  <Link
                    href={`/auth/organisations/${c.organisation_id}`}
                    className="hover:underline"
                  >
                    {orgName(c.organisation_id)}
                  </Link>
                </td>
                <td className="w-72 px-4 py-2">
                  <InlineEmailCell
                    contactId={c.id}
                    currentEmail={c.email}
                    invalidateKeys={[["contacts"], ["contact", c.id]]}
                  />
                </td>
                <td className="px-4 py-2">
                  <Badge variant="secondary">{c.status}</Badge>
                </td>
                <td className="px-4 py-2 text-right">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setPendingDelete(c)}
                    aria-label={`Delete ${c.first_name} ${c.last_name}`}
                  >
                    Delete
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {contactsQuery.data && (
        <p className="text-xs text-muted-foreground">
          Showing {contactsQuery.data.items.length} of {contactsQuery.data.total} matching
          contacts.
        </p>
      )}
    </div>
  );
}
