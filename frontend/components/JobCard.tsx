"use client";

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
          {isNew && <span className="badge badge--new">NEW</span>}
          {job.datetime && <span className="card__time">{job.datetime}</span>}
        </div>

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

        {job.estimate && <div className="card__estimate">{job.estimate}</div>}

        {job.content && <pre className="card__content">{job.content}</pre>}

        <div className="card__footer">
          {job.url && (
            <a
              className="card__link"
              href={job.url}
              target="_blank"
              rel="noopener noreferrer"
            >
              Open detail ↗
            </a>
          )}
          <CopyButton text={copyText} />
        </div>
      </div>
    </article>
  );
}
