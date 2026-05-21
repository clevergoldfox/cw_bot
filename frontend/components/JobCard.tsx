"use client";

import { useState } from "react";
import CopyButton from "./CopyButton";
import type { Job } from "@/lib/types";

const AUTHOR: Record<Job["channel"], string> = {
  crowdworks: "Crowdworks Bot",
  lancers: "Lancers Bot",
};

const AVATAR: Record<Job["channel"], string> = {
  crowdworks: "CW",
  lancers: "LA",
};

export default function JobCard({ job, isNew }: { job: Job; isNew: boolean }) {
  const [open, setOpen] = useState(false);

  // Exactly the text the Slack code block used.
  const copyText =
    `Title:${job.title}\n` + "-".repeat(19) + `\n Content:${job.content}`;

  return (
    <article className={`card ${isNew ? "card--new" : ""}`}>
      <div className={`card__avatar card__avatar--${job.channel}`}>
        {AVATAR[job.channel]}
      </div>

      <div className="card__body">
        <div className="card__head">
          <span className="card__author">{AUTHOR[job.channel]}</span>
          {job.category && <span className="badge">{job.category}</span>}
          {job.estimate && <span className="card__estimate">{job.estimate}</span>}
          {isNew && <span className="badge badge--new">NEW</span>}
          {job.datetime && <span className="card__time">{job.datetime}</span>}
        </div>

        <div className="card__titlerow">
          {job.url ? (
            <a
              className="card__title"
              href={job.url}
              target="_blank"
              rel="noopener noreferrer"
            >
              {job.title}
            </a>
          ) : (
            <span className="card__title card__title--plain">{job.title}</span>
          )}

          <div className="card__actions">
            <CopyButton text={copyText} />
            <button
              type="button"
              className="toggle-btn"
              onClick={() => setOpen((v) => !v)}
              aria-expanded={open}
              aria-label={open ? "Collapse details" : "Expand details"}
            >
              {open ? "−" : "+"}
            </button>
          </div>
        </div>

        {open && (
          <div className="card__dropdown">
            <div className="card__dropdown-label">Title</div>
            <div className="card__dropdown-title">{job.title}</div>
            <div className="card__dropdown-label">Content</div>
            <pre className="card__content">{job.content || "(no content)"}</pre>
          </div>
        )}
      </div>
    </article>
  );
}
