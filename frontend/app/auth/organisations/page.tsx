"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { apiDelete, apiGet, apiPost, ApiError } from "@/lib/api";
import type { Organisation, Paginated } from "@/lib/types";

interface Notice {
  kind: "success" | "error";
  message: string;
}

export default function OrganisationsPage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState("");
  const [domain, setDomain] = useState("");
  const [notes, setNotes] = useState("");
  const [notice, setNotice] = useState<Notice | null>(null);

  const listQuery = useQuery({
    queryKey: ["organisations", search],
    queryFn: () =>
      apiGet<Paginated<Organisation>>(
        `/organisations?limit=100${search ? `&q=${encodeURIComponent(search)}` : ""}`,
      ),
  });

  const create = useMutation({
    mutationFn: () =>
      apiPost<Organisation>("/organisations", {
        name,
        domain: domain || null,
        notes,
      }),
    onSuccess: async () => {
      setName("");
      setDomain("");
      setNotes("");
      setShowCreate(false);
      setNotice({ kind: "success", message: "Organisation created." });
      await qc.invalidateQueries({ queryKey: ["organisations"] });
    },
    onError: (err) => {
      setNotice({
        kind: "error",
        message: err instanceof ApiError ? err.message : "Create failed.",
      });
    },
  });

  const remove = useMutation({
    mutationFn: (id: number) => apiDelete<void>(`/organisations/${id}`),
    onSuccess: async () => {
      setNotice({ kind: "success", message: "Organisation deleted." });
      await qc.invalidateQueries({ queryKey: ["organisations"] });
    },
    onError: (err) => {
      setNotice({
        kind: "error",
        message: err instanceof ApiError ? err.message : "Delete failed.",
      });
    },
  });

  function askDelete(o: Organisation) {
    if (!confirm(`Delete "${o.name}"? This is blocked if it has contacts.`)) return;
    remove.mutate(o.id);
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Organisations</h1>
          <p className="text-sm text-muted-foreground">
            The reusable company database. Contacts belong here.
          </p>
        </div>
        <Button onClick={() => setShowCreate((v) => !v)}>
          {showCreate ? "Cancel" : "New organisation"}
        </Button>
      </div>

      {showCreate && (
        <Card>
          <CardHeader>
            <CardTitle>Create organisation</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-2">
              <Label htmlFor="new-name">Name</Label>
              <Input id="new-name" value={name} onChange={(e) => setName(e.target.value)} required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="new-domain">Domain</Label>
              <Input
                id="new-domain"
                placeholder="acme.com"
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="new-notes">Notes</Label>
              <Textarea
                id="new-notes"
                rows={3}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
            </div>
            <Button
              onClick={() => create.mutate()}
              disabled={!name || create.isPending}
            >
              {create.isPending ? "Creating…" : "Create"}
            </Button>
          </CardContent>
        </Card>
      )}

      {notice && (
        <p
          className={notice.kind === "error" ? "text-sm text-destructive" : "text-sm text-emerald-600"}
        >
          {notice.message}
        </p>
      )}

      <div className="flex items-center gap-3">
        <Input
          placeholder="Search by name or domain…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-sm"
        />
      </div>

      <div className="rounded-md border">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-left">
            <tr>
              <th className="px-4 py-2 font-medium">Name</th>
              <th className="px-4 py-2 font-medium">Domain</th>
              <th className="px-4 py-2 font-medium">Created</th>
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
            {listQuery.data?.items.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-4 text-muted-foreground">
                  No organisations found.
                </td>
              </tr>
            )}
            {(listQuery.data?.items ?? []).map((o) => (
              <tr key={o.id} className="border-t">
                <td className="px-4 py-2">
                  <Link href={`/auth/organisations/${o.id}`} className="font-medium hover:underline">
                    {o.name}
                  </Link>
                </td>
                <td className="px-4 py-2 text-muted-foreground">{o.domain ?? "—"}</td>
                <td className="px-4 py-2 text-muted-foreground">
                  {new Date(o.created_at).toLocaleDateString()}
                </td>
                <td className="px-4 py-2 text-right">
                  <Button variant="ghost" size="sm" onClick={() => askDelete(o)}>
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
