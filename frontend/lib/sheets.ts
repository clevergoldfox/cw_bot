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

const EXPECTED_HOST: Record<Channel, string> = {
  crowdworks: "crowdworks.jp",
  lancers: "lancers.jp",
};

/** Extract the URL out of a `=HYPERLINK("url","title")` cell formula. */
function parseHyperlinkUrl(formula: string): string {
  const match = /HYPERLINK\("([^"]+)"/i.exec(formula || "");
  return match ? match[1] : "";
}

function valuesUrl(range: string, render: "FORMATTED_VALUE" | "FORMULA"): string {
  return (
    `https://sheets.googleapis.com/v4/spreadsheets/${SHEET_ID}` +
    `/values/${encodeURIComponent(range)}?valueRenderOption=${render}`
  );
}

/**
 * Read one channel's tab. Columns written by the Python watchers are:
 * A datetime · B category · C title · D estimate · E content · F detail url.
 * Returned newest-first.
 */
export async function readChannel(channel: Channel): Promise<Job[]> {
  const tab = TABS[channel];
  const client = getClient();

  // Column F can be stale (e.g. a fill-down overwrote it), so the real detail
  // link is read from column C's HYPERLINK formula instead.
  const [fmtRes, formulaRes] = await Promise.all([
    client.request<{ values?: string[][] }>({
      url: valuesUrl(`${tab}!A1:F2000`, "FORMATTED_VALUE"),
    }),
    client.request<{ values?: string[][] }>({
      url: valuesUrl(`${tab}!C1:C2000`, "FORMULA"),
    }),
  ]);

  const rows = fmtRes.data.values || [];
  const formulaRows = formulaRes.data.values || [];
  const expectedHost = EXPECTED_HOST[channel];

  const jobs: Job[] = [];
  rows.forEach((row, i) => {
    const datetime = (row[0] || "").trim();
    const category = (row[1] || "").trim();
    const title = (row[2] || "").trim();
    const estimate = (row[3] || "").trim();
    const content = row[4] || "";
    const colF = (row[5] || "").trim();

    if (!title) return; // skip blank rows

    const url = parseHyperlinkUrl(formulaRows[i]?.[0] || "") || colF;

    // Guard: never let a mis-filed row leak into the wrong channel.
    if (url && !url.includes(expectedHost)) return;

    jobs.push({
      // Row-number based id — unique and stable per row, so React keys never
      // collide even when several jobs share a URL.
      id: `${channel}-${i + 1}`,
      datetime,
      category,
      title,
      estimate,
      content,
      url,
      channel,
    });
  });

  return jobs.reverse(); // newest row is last in the sheet
}
