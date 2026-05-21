# Job Watcher — Frontend

A Slack-style web feed for the new assignments collected by `lancers.py` and
`index.py`. It reads the same Google Sheet the watchers write to and shows each
assignment as a message card with a **green Copy button** that copies

```
Title:{Assignment Title}
-------------------
 Content:{Assignment Content}
```

to the clipboard — the thing Slack itself cannot do.

## How it works

- The Python watchers append rows to the spreadsheet (tabs `CW` and `Lancers`).
- This Next.js app reads those tabs through the Google Sheets API
  (`/api/jobs`) and renders them.
- The browser re-polls every 20 seconds; newly-arrived assignments flash once.

No database — the Google Sheet is the single source of truth.

## Local development

```bash
cd frontend
npm install
cp .env.local.example .env.local   # then fill in the values
npm run dev                        # http://localhost:3000
```

### Environment variables

All three come from `service_account.json` (the same file the Python scripts use):

| Variable               | Value                                                        |
| ---------------------- | ------------------------------------------------------------ |
| `GOOGLE_SHEET_ID`      | `1-PL8BvUVVczQ86XJY_e3wm8BMHs3fU4AzBeoI6Yryvk`               |
| `GOOGLE_CLIENT_EMAIL`  | the `client_email` field                                    |
| `GOOGLE_PRIVATE_KEY`   | the `private_key` field (one line, literal `\n`, in quotes)  |

The service account only needs **read** access to the spreadsheet — it is
already shared with it.

## Deploy to Vercel

1. Push this repository to GitHub/GitLab.
2. In Vercel, **New Project** → import the repo.
3. Set **Root Directory** to `frontend` (skip if the repo root *is* this folder).
4. Set **Framework Preset** to **Next.js**. This is required — if it is left on
   "Other", the build fails with `No Output Directory named "public" found`.
   `vercel.json` in this folder also pins `"framework": "nextjs"` as a safeguard.
5. Under **Environment Variables**, add the three variables above
   (`GOOGLE_SHEET_ID`, `GOOGLE_CLIENT_EMAIL`, `GOOGLE_PRIVATE_KEY`).
   - For `GOOGLE_PRIVATE_KEY`, paste the key value including the
     `-----BEGIN PRIVATE KEY-----` / `-----END PRIVATE KEY-----` lines. Vercel
     accepts either real newlines or literal `\n` — the app handles both.
6. **Deploy**.

To redeploy after a credentials change, update the env vars and trigger a new
deployment.

## Project layout

```
frontend/
  app/
    api/jobs/route.ts   # reads both sheet tabs, returns JSON
    page.tsx            # client page: polling + channel state
    layout.tsx
    globals.css         # Slack-style theme
  components/
    Sidebar.tsx         # channel switcher (#crowdworks / #lancers)
    JobFeed.tsx         # message feed + header
    JobCard.tsx         # one assignment card
    CopyButton.tsx      # green clipboard button
  lib/
    sheets.ts           # Google Sheets read layer
    types.ts
```
