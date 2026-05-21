import { NextResponse } from "next/server";
import { readChannel } from "@/lib/sheets";
import type { JobsResponse } from "@/lib/types";

// Always run fresh on the server (no static caching of the response).
export const dynamic = "force-dynamic";

// Small in-memory cache so multiple browser clients polling at once don't
// each hit the Sheets API. Short TTL keeps the feed near real-time.
const TTL_MS = 8000;
let cache: { at: number; data: JobsResponse } | null = null;

export async function GET() {
  if (cache && Date.now() - cache.at < TTL_MS) {
    return NextResponse.json(cache.data);
  }

  try {
    const [crowdworks, lancers] = await Promise.all([
      readChannel("crowdworks"),
      readChannel("lancers"),
    ]);
    const data: JobsResponse = { crowdworks, lancers };
    cache = { at: Date.now(), data };
    return NextResponse.json(data);
  } catch (err) {
    const message =
      err instanceof Error ? err.message : "Failed to load jobs from Google Sheets.";
    // Return 200 with an error field so the UI can show a friendly message.
    return NextResponse.json({ crowdworks: [], lancers: [], error: message });
  }
}
