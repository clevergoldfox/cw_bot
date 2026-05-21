export type Channel = "crowdworks" | "lancers";

export interface Job {
  /** Stable id — the detail URL when available, else channel+row index. */
  id: string;
  datetime: string;
  category: string;
  title: string;
  estimate: string;
  content: string;
  url: string;
  channel: Channel;
}

export interface JobsResponse {
  crowdworks: Job[];
  lancers: Job[];
  /** Set when the sheet could not be read (e.g. missing credentials). */
  error?: string;
}
