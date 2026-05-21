"use client";

import JobCard from "./JobCard";
import type { Channel, Job } from "@/lib/types";

const CHANNEL_LABEL: Record<Channel, string> = {
  crowdworks: "crowdworks",
  lancers: "lancers",
};

export default function JobFeed({
  channel,
  jobs,
  loading,
  error,
  lastUpdated,
  readIds,
  justArrived,
  onMarkRead,
  notifPermission,
  onEnableNotifications,
  onRefresh,
}: {
  channel: Channel;
  jobs: Job[];
  loading: boolean;
  error?: string;
  lastUpdated: Date | null;
  readIds: Set<string>;
  justArrived: Set<string>;
  onMarkRead: (id: string) => void;
  notifPermission: NotificationPermission;
  onEnableNotifications: () => void;
  onRefresh: () => void;
}) {
  return (
    <main className="feed">
      <header className="feed__header">
        <div className="feed__heading">
          <span className="feed__hash">#</span>
          <span className="feed__channel">{CHANNEL_LABEL[channel]}</span>
        </div>
        <div className="feed__meta">
          {notifPermission !== "granted" && (
            <button className="feed__notify" onClick={onEnableNotifications}>
              🔔 Enable notifications
            </button>
          )}
          <span>{jobs.length} assignments</span>
          {lastUpdated && (
            <span className="feed__updated">
              updated {lastUpdated.toLocaleTimeString()}
            </span>
          )}
          <button className="feed__refresh" onClick={onRefresh}>
            Refresh
          </button>
        </div>
      </header>

      <div className="feed__body">
        {error && (
          <div className="feed__error">
            <strong>Could not load assignments.</strong>
            <span>{error}</span>
          </div>
        )}

        {loading && jobs.length === 0 && !error && (
          <div className="feed__placeholder">Loading assignments…</div>
        )}

        {!loading && !error && jobs.length === 0 && (
          <div className="feed__placeholder">
            No assignments in #{CHANNEL_LABEL[channel]} yet.
          </div>
        )}

        {jobs.map((job) => (
          <JobCard
            key={job.id}
            job={job}
            unread={!readIds.has(job.id)}
            justArrived={justArrived.has(job.id)}
            onMarkRead={onMarkRead}
          />
        ))}
      </div>
    </main>
  );
}
