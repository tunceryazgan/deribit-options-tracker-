# Deribit SOL & HYPE Options Tracker

Deribit is blocked in Turkey, so direct API calls from a Turkish IP (browser
or local script) don't work. This setup offloads the data fetching to
GitHub Actions (US/EU runners), and you read the result locally with
`dashboard.html` — no VPN needed for day-to-day use.

## Setup (~5 minutes, one-time)

1. **Create a new public GitHub repo** (e.g. `deribit-options-tracker`).

2. **Upload these files, keeping the exact folder structure:**
   ```
   deribit-options-tracker/
   ├── poll_deribit.py
   └── .github/
       └── workflows/
           └── poll.yml
   ```
   This is the part that's easy to get wrong: GitHub only recognizes a
   workflow if the file lives at exactly `.github/workflows/poll.yml`.
   If you use the web UI, click **Add file → Create new file** and type
   the full path `.github/workflows/poll.yml` into the filename box —
   GitHub will create the folders automatically. Don't just upload
   `poll.yml` to the repo root; it will be silently ignored.

   You don't need to upload `dashboard.html` to the repo — just keep it
   on your own machine.

3. **Trigger the workflow once manually:**
   Repo → **Actions** tab → **Poll Deribit Options Data** → **Run workflow**.
   It finishes in ~30 seconds and creates `data/latest.json` and
   `data/history.csv` in your repo. After that, GitHub runs it
   automatically every 15 minutes.

4. **Open `dashboard.html`** on your computer (just double-click it).
   In the top-right **⚙ Repo Settings** panel, enter:
   - your GitHub username
   - your repo name (copy it exactly — including any trailing characters)
   - branch: `main`

   Click **Save & Load**. This is stored in your browser, so you won't
   need to re-enter it next time.

## How it works

```
GitHub Actions (every 15 min, US/EU server)
   -> calls Deribit's API (no Turkey block there)
   -> updates data/latest.json + data/history.csv, pushes to the repo
        |
        v
dashboard.html (your machine, Turkey, no VPN)
   -> reads those two files from raw.githubusercontent.com
   -> auto-refreshes every 60s (underlying data changes every ~15 min)
```

## Notes

- Data can lag up to ~15 minutes (GitHub's schedule interval). That's
  fine for tracking overall volume, not for tick-by-tick trading.
- `data/history.csv` grows over time; if it gets large after months of
  running, we can add a step that trims old rows.
- The workflow needs `permissions: contents: write`, which is already
  in `poll.yml` -- no extra repo setting required for a normal repo.
- You can shorten the interval by editing `cron: '*/15 * * * *'` in
  `.github/workflows/poll.yml` (GitHub's practical minimum is ~5 min;
  shorter than that and runs tend to queue/delay).

## Troubleshooting

- **Dashboard shows "connection error"**: double check the username/repo
  name in the config panel -- a typo (or a missing trailing character in
  the repo name) is the most common cause.
- **Actions tab shows no workflow**: the YAML file isn't at
  `.github/workflows/poll.yml`. Re-check the path.
- **Workflow runs but `data/` never appears**: open the run's log in the
  Actions tab and check the "Fetch Deribit data" and "Commit and push"
  steps for errors.
