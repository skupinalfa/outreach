"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import type { ActivityMessageSnapshot } from "@/lib/types";

const TRUNCATE_AT = 2000;

interface Props {
  snapshot: ActivityMessageSnapshot;
}

export function ActivityBodyExpand({ snapshot }: Props) {
  const [showFull, setShowFull] = useState(false);
  const needsTruncation = snapshot.body.length > TRUNCATE_AT;
  const displayed = showFull || !needsTruncation ? snapshot.body : snapshot.body.slice(0, TRUNCATE_AT);

  return (
    <div className="mt-2 space-y-2 rounded-md border bg-muted/30 p-3 text-sm">
      <div>
        <span className="text-muted-foreground">Subject:</span>{" "}
        <span className="font-medium">{snapshot.subject}</span>
      </div>
      <pre className="whitespace-pre-wrap font-sans text-sm text-foreground">
        {displayed}
        {needsTruncation && !showFull ? "…" : ""}
      </pre>
      {needsTruncation && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => setShowFull((v) => !v)}
        >
          {showFull ? "Show less" : `Show more (${snapshot.body.length - TRUNCATE_AT} chars)`}
        </Button>
      )}
      {snapshot.delivery_status && (
        <p className="text-xs text-muted-foreground">
          Delivery status: {snapshot.delivery_status}
        </p>
      )}
    </div>
  );
}
