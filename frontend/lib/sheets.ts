import { JWT } from "google-auth-library";
import type { Channel, Job } from "./types";

const SHEET_ID =
  process.env.GOOGLE_SHEET_ID || "1-PL8BvUVVczQ86XJY_e3wm8BMHs3fU4AzBeoI6Yryvk";

// Tab names inside the spreadsheet (must match lancers.py / index.py targets).
const TABS: Record<Channel, string> = {
  crowdworks: "CW",
  lancers: "Lancers",
};

let cachedClient: JWT | null = null;

function getClient(): JWT {
  if (cachedClient) return cachedClient;

  const email = process.env.GOOGLE_CLIENT_EMAIL;
  // Vercel stores newlines literally as "\n" — restore real newlines.
  const key = process.env.GOOGLE_PRIVATE_KEY?.replace(/\\n/g, "\n");

  if (!email || !key) {
    throw new Error(
      "Missing GOOGLE_CLIENT_EMAIL / GOOGLE_PRIVATE_KEY environment variables.",
    );
  }

  cachedClient = new JWT({
    email,
    key,
    scopes: ["https://www.googleapis.com/auth/spreadsheets.readonly"],
  });
  return cachedClient;
}

/**
 * Read one channel's tab. Columns written by the Python watchers are:
 * A datetime · B category · C title · D estimate · E content · F detail url.
 * Returned newest-first.
 */
export async function readChannel(channel: Channel): Promise<Job[]> {
  const range = `${TABS[channel]}!A1:F2000`;
  const url =
    `https://sheets.googleapis.com/v4/spreadsheets/${SHEET_ID}` +
    `/values/${encodeURIComponent(range)}?valueRenderOption=FORMATTED_VALUE`;

  const res = await getClient().request<{ values?: string[][] }>({ url });
  const rows = res.data.values || [];

  const jobs: Job[] = [];
  rows.forEach((row, i) => {
    const datetime = (row[0] || "").trim();
    const category = (row[1] || "").trim();
    const title = (row[2] || "").trim();
    const estimate = (row[3] || "").trim();
    const content = row[4] || "";
    const detailUrl = (row[5] || "").trim();

    if (!title) return; // skip blank rows

    jobs.push({
      id: detailUrl || `${channel}-${i}`,
      datetime,
      category,
      title,
      estimate,
      content,
      url: detailUrl,
      channel,
    });
  });

  return jobs.reverse(); // newest row is last in the sheet
}
