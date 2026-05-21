"use client";

import type { Channel } from "@/lib/types";

const CHANNELS: { key: Channel; label: string }[] = [
  { key: "crowdworks", label: "crowdworks" },
  { key: "lancers", label: "lancers" },
];

export default function Sidebar({
  channel,
  onSelect,
  counts,
}: {
  channel: Channel;
  onSelect: (c: Channel) => void;
  counts: Record<Channel, number>;
}) {
  return (
    <aside className="sidebar">
      <div className="sidebar__workspace">
        <div className="sidebar__logo">JW</div>
        <div>
          <div className="sidebar__title">Job Watcher</div>
          <div className="sidebar__subtitle">live assignment feed</div>
        </div>
      </div>

      <div className="sidebar__section">Channels</div>
      <nav className="sidebar__channels">
        {CHANNELS.map((c) => (
          <button
            key={c.key}
            className={`channel ${channel === c.key ? "channel--active" : ""}`}
            onClick={() => onSelect(c.key)}
          >
            <span className="channel__hash">#</span>
            <span className="channel__name">{c.label}</span>
            <span className="channel__count">{counts[c.key]}</span>
          </button>
        ))}
      </nav>
    </aside>
  );
}
