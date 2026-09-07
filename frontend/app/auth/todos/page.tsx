"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { apiGet } from "@/lib/api";
import type { Paginated, Todo } from "@/lib/types";

function badgeVariantFor(type: Todo["type"]) {
  if (type === "send") return "default" as const;
  if (type === "follow_up") return "secondary" as const;
  return "outline" as const;
}

export default function TodosPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["todos", "open-scheduled"],
    queryFn: () => apiGet<Paginated<Todo>>("/todos?status=open&limit=100"),
    refetchInterval: 30_000,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Todos</h1>
        <p className="text-sm text-muted-foreground">
          Open work — sends and follow-ups queued for action.
        </p>
      </div>

      {isLoading && <p>Loading…</p>}
      {isError && <p className="text-destructive">Could not load todos.</p>}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {(data?.items ?? []).map((todo) => (
          <Link key={todo.id} href={`/auth/todos/${todo.id}`} className="block">
            <Card className="transition-colors hover:bg-muted/50">
              <CardHeader className="space-y-2">
                <div className="flex items-center gap-2">
                  <Badge variant={badgeVariantFor(todo.type)}>{todo.type}</Badge>
                  <span className="text-xs text-muted-foreground">
                    Due {new Date(todo.due_at).toLocaleString()}
                  </span>
                </div>
                <CardTitle className="text-base">{todo.title}</CardTitle>
              </CardHeader>
              <CardContent className="text-xs text-muted-foreground">
                Status: {todo.status}
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>

      {data && data.items.length === 0 && (
        <p className="text-sm text-muted-foreground">Nothing open right now.</p>
      )}
    </div>
  );
}
