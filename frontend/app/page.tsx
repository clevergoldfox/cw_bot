"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Sidebar from "@/components/Sidebar";
import JobFeed from "@/components/JobFeed";
import type { Channel, Job, JobsResponse } from "@/lib/types";

const POLL_MS = 20000;
const READ_KEY = "jobwatcher.readIds.v1";
const NOTIFY_AUTOCLOSE_MS = 5000;

/** Read the persisted set of "read" job ids; null when never stored before. */
function loadReadIds(): Set<string> | null {
  try {
    const raw = localStorage.getItem(READ_KEY);
    if (raw === null) return null;
    return new Set(JSON.parse(raw) as string[]);
  } catch {
    return null;
  }
}

function saveReadIds(ids: Set<string>) {
  try {
    localStorage.setItem(READ_KEY, JSON.stringify([...ids]));
  } catch {
    /* storage disabled / over quota — ignore */
  }
}

export default function Home() {
  const [channel, setChannel] = useState<Channel>("crowdworks");
  const [data, setData] = useState<JobsResponse>({ crowdworks: [], lancers: [] });
  const [loading, setLoading] = useState(true);
  const [initialized, setInitialized] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  // Jobs the user has already dealt with (interacted with, or present at the
  // very first visit). Persisted in localStorage. A job is "new/unread" while
  // its id is NOT in this set.
  const [readIds, setReadIds] = useState<Set<string>>(new Set());
  // Jobs that arrived during this poll — drives the one-shot arrival flash.
  const [justArrived, setJustArrived] = useState<Set<string>>(new Set());
  const [notifPermission, setNotifPermission] =
    useState<NotificationPermission>("default");

  // Every job id seen so far this browser session (notification de-dup).
  const knownIds = useRef<Set<string> | null>(null);

  // --- desktop notifications -------------------------------------------------
  const notify = useCallback((jobs: Job[]) => {
    if (typeof window === "undefined" || !("Notification" in window)) return;
    if (Notification.permission !== "granted") return;

    const popOne = (title: string, body: string, tag: string, url?: string) => {
      try {
        const n = new Notification(title, { body, tag });
        if (url) {
          n.onclick = () => {
            window.open(url, "_blank");
            n.close();
          };
        }
        // Keep it on screen for 5 seconds, then dismiss.
        window.setTimeout(() => n.close(), NOTIFY_AUTOCLOSE_MS);
      } catch {
        /* ignore */
      }
    };

    if (jobs.length <= 3) {
      for (const j of jobs) {
        const label = j.channel === "crowdworks" ? "Crowdworks" : "Lancers";
        popOne(`New ${label} assignment`, j.title, j.id, j.url || undefined);
      }
    } else {
      popOne(
        "New assignments",
        `${jobs.length} new assignments were posted.`,
        "jobwatcher-batch",
      );
    }
  }, []);

  // --- polling ---------------------------------------------------------------
  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/jobs", { cache: "no-store" });
      const json: JobsResponse = await res.json();
      const allJobs = [...json.crowdworks, ...json.lancers];
      const allIds = allJobs.map((j) => j.id);

      if (knownIds.current === null) {
        // First load this session.
        knownIds.current = new Set(allIds);
        const stored = loadReadIds();
        if (stored === null) {
          // First visit ever — everything already posted is the baseline.
          const baseline = new Set(allIds);
          saveReadIds(baseline);
          setReadIds(baseline);
        } else {
          setReadIds(stored);
        }
      } else {
        // Later poll — anything not seen before is a genuinely new assignment.
        const arrived = allJobs.filter((j) => !knownIds.current!.has(j.id));
        if (arrived.length > 0) {
          arrived.forEach((j) => knownIds.current!.add(j.id));
          setJustArrived(new Set(arrived.map((j) => j.id)));
          notify(arrived);
        }
      }

      setData(json);
      setLastUpdated(new Date());
      setInitialized(true);
    } catch {
      // Network hiccup — keep showing the previous data.
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    load();
    const timer = setInterval(load, POLL_MS);
    return () => clearInterval(timer);
  }, [load]);

  // Ask for notification permission once on mount.
  useEffect(() => {
    if (typeof window === "undefined" || !("Notification" in window)) return;
    setNotifPermission(Notification.permission);
    if (Notification.permission === "default") {
      Notification.requestPermission()
        .then(setNotifPermission)
        .catch(() => {});
    }
  }, []);

  const enableNotifications = useCallback(() => {
    if (typeof window === "undefined" || !("Notification" in window)) return;
    Notification.requestPermission()
      .then(setNotifPermission)
      .catch(() => {});
  }, []);

  // Mark a job read when the user interacts with it (+/- toggle or copy).
  const markRead = useCallback((id: string) => {
    setReadIds((prev) => {
      if (prev.has(id)) return prev;
      const next = new Set(prev);
      next.add(id);
      saveReadIds(next);
      return next;
    });
  }, []);

  const unreadCount = (list: Job[]) =>
    list.reduce((n, j) => (readIds.has(j.id) ? n : n + 1), 0);

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
        unread={{
          crowdworks: initialized ? unreadCount(data.crowdworks) : 0,
          lancers: initialized ? unreadCount(data.lancers) : 0,
        }}
      />
      <JobFeed
        channel={channel}
        jobs={jobs}
        loading={loading}
        error={data.error}
        lastUpdated={lastUpdated}
        readIds={readIds}
        justArrived={justArrived}
        onMarkRead={markRead}
        notifPermission={notifPermission}
        onEnableNotifications={enableNotifications}
        onRefresh={load}
      />
    </div>
  );
}
