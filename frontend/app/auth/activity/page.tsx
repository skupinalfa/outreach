"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ActivityFilters, activityFilterQuery } from "@/components/activity/ActivityFilters";
import type { ActivityFiltersState } from "@/components/activity/ActivityFilters";
import { ActivityRow } from "@/components/activity/ActivityRow";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { apiGet } from "@/lib/api";
import type { GlobalActivityResponse } from "@/lib/types";

const INITIAL_FILTERS: ActivityFiltersState = {
  eventTypes: [],
  contactId: null,
  organisationId: null,
  window: "",
};

export default function ActivityPage() {
  const router = useRouter();
  const [filters, setFilters] = useState<ActivityFiltersState>(INITIAL_FILTERS);

  const query = useInfiniteQuery({
    queryKey: ["activity", filters],
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) => {
      const params = activityFilterQuery(filters);
      params.set("limit", "50");
      if (pageParam) params.set("cursor", pageParam);
      const qs = params.toString();
      return apiGet<GlobalActivityResponse>(`/activity${qs ? `?${qs}` : ""}`);
    },
    getNextPageParam: (last) => (last.has_more ? last.next_cursor : undefined),
  });

  const items = query.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <div className="max-w-4xl space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Activity</h1>
        <p className="text-sm text-muted-foreground">
          Every outreach event across all contacts, newest first.
        </p>
      </div>

      <ActivityFilters value={filters} onChange={setFilters} />

      <Card>
        <CardHeader>
          <CardTitle>Timeline</CardTitle>
        </CardHeader>
        <CardContent>
          {query.isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
          {query.isError && (
            <p className="text-sm text-destructive">Could not load activity.</p>
          )}
          {query.data && items.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No activity matches the current filters.
            </p>
          )}
          {items.length > 0 && (
            <ul className="divide-y">
              {items.map((event) => (
                <ActivityRow
                  key={event.id}
                  event={event}
                  showContact
                  onSelectContact={(id) => router.push(`/auth/leads/${id}?tab=activity`)}
                />
              ))}
            </ul>
          )}
          {query.hasNextPage && (
            <div className="mt-4">
              <Button
                type="button"
                variant="outline"
                onClick={() => query.fetchNextPage()}
                disabled={query.isFetchingNextPage}
              >
                {query.isFetchingNextPage ? "Loading…" : "Load more"}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
