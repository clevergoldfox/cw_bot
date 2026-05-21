"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Sidebar from "@/components/Sidebar";
import JobFeed from "@/components/JobFeed";
import type { Channel, JobsResponse } from "@/lib/types";

const POLL_MS = 20000;

export default function Home() {
  const [channel, setChannel] = useState<Channel>("crowdworks");
  const [data, setData] = useState<JobsResponse>({ crowdworks: [], lancers: [] });
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [newIds, setNewIds] = useState<Set<string>>(new Set());

  // Track which job ids have already been seen so freshly-arrived jobs can
  // be highlighted. Populated silently on the first load.
  const seenIds = useRef<Set<string> | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/jobs", { cache: "no-store" });
      const json: JobsResponse = await res.json();

      const allIds = [...json.crowdworks, ...json.lancers].map((j) => j.id);
      if (seenIds.current === null) {
        seenIds.current = new Set(allIds); // first load: nothing is "new"
      } else {
        const fresh = new Set<string>();
        for (const id of allIds) {
          if (!seenIds.current.has(id)) {
            fresh.add(id);
            seenIds.current.add(id);
          }
        }
        if (fresh.size > 0) setNewIds(fresh);
      }

      setData(json);
      setLastUpdated(new Date());
    } catch {
      // Network hiccup — keep showing the previous data.
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(load, POLL_MS);
    return () => clearInterval(timer);
  }, [load]);

  const jobs = channel === "crowdworks" ? data.crowdworks : data.lancers;

  return (
    <div className="app">
      <Sidebar
        channel={channel}
        onSelect={setChannel}
        counts={{
          crowdworks: data.crowdworks.length,
          lancers: data.lancers.length,
        }}
      />
      <JobFeed
        channel={channel}
        jobs={jobs}
        loading={loading}
        error={data.error}
        lastUpdated={lastUpdated}
        newIds={newIds}
        onRefresh={load}
      />
    </div>
  );
}
