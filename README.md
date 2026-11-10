# ipo-calendar-sync

Automatically add Japanese IPO book-building periods to your Google Calendar.

Once a day, a GitHub Actions workflow reads the public IPO list on the SBI Securities website, extracts the book-building (subscription) period of each new IPO, and creates one Google Calendar event per company. No server, no computer of your own needs to stay on, and no securities account login is used.

## What it does

- **Source**: the public SBI Securities IPO page (static HTML, Shift_JIS). Only the "IPO (新規上場株)" section is used; public offerings ("PO") are ignored. Issuers whose period is not decided yet (shown as `-`) are skipped until it is.
- **One event per IPO** spanning the book-building period, for example `【IPOブックビル期間】Example Corp` from 11/24 0:00 to 11/27 11:00 JST.
- **Description** (in Japanese, as on the source page): period, ticker code and market, price-range decision date, allocation (lottery) date, listing date, a dedupe key, and the source URL.
- **Safe by design**:
  - Duplicates are detected with the dedupe key, so re-running is harmless.
  - Existing events are never modified or deleted. If a company's dates change, the run reports a possible date change instead of editing.
  - IPOs whose period has already ended are not added.
  - No video-call (Meet) links are added.
- **Fails loudly**: if the page cannot be fetched, the layout changes, zero IPOs are found, or the Calendar API fails, the run fails, so GitHub emails you. An optional Discord notification can be added.

Defaults (all configurable, see [Configuration](#configuration)): yellow event color, shown as "free" so it does not block your schedule, reminders at 19:00 the day before and 30 minutes before.

## Setup

You need a GitHub account and a Google account. Everything below fits in the free tiers: the Google Calendar API has no charge for standard use, and the workflow takes about 30 seconds a day.

### 1. Put the code in your own repository

```sh
git clone https://github.com/genchan-omega/ipo-calendar-sync-public.git
cd ipo-calendar-sync-public
git remote set-url origin https://github.com/<you>/<your-repo>.git   # create an empty repo first
git push -u origin main
```

A private repository is recommended. (In a forked repository, scheduled workflows are disabled until you enable them in the Actions tab.)

### 2. Create a Google service account

The workflow runs on GitHub's servers, so it needs its own Google identity: a service account. It can only touch calendars you explicitly share with it.

1. Open the [Google Cloud console](https://console.cloud.google.com/) and create a project (any name).
2. In **APIs & Services → Library**, find **Google Calendar API** and click **Enable**.
3. In **IAM & Admin → Service accounts**, click **Create service account**. Give it a name and skip the optional role step: no roles are needed. Copy its email address (`...@<project>.iam.gserviceaccount.com`).
4. Open the service account, go to **Keys → Add key → Create new key → JSON**. A JSON key file is downloaded. Treat it like a password and never commit it.

### 3. Share your calendar with the service account

In Google Calendar, open **Settings → (your calendar) → Share with specific people → Add people**. Paste the service account email and choose **Make changes to events**.

### 4. Add the secrets to your repository

In your repository, go to **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Value |
| --- | --- |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | the whole content of the JSON key file |
| `GOOGLE_CALENDAR_ID` | your calendar ID. For your main calendar, this is your Gmail address. For other calendars, see **Settings → (calendar) → Integrate calendar → Calendar ID**. |
| `DISCORD_WEBHOOK_URL` | optional. A Discord webhook URL to get notified about new events, date changes and failures. |

Then delete the downloaded JSON file from your computer.

### 5. Check it works

In the **Actions** tab, open **sync-ipo-calendar → Run workflow** and run it in this order:

1. **selftest** checked: creates a test event in 2030, reads it back and deletes it. This confirms the key and the calendar sharing.
2. **dry_run** checked: shows which IPOs would be added, without writing anything.
3. Neither checked: the real run.

The results appear in the run's summary page. After this, the workflow runs every day at 01:30 JST.

## Configuration

Optional. Set these in **Settings → Secrets and variables → Actions → Variables**. Leave a variable unset to keep the default.

| Variable | Default | Meaning |
| --- | --- | --- |
| `IPO_TITLE_PREFIX` | `【IPOブックビル期間】` | Text placed before the company name in the event title. |
| `IPO_COLOR_ID` | `5` (yellow) | Google Calendar event color, `1`–`11`, or `none` for the calendar's default color. |
| `IPO_REMINDERS` | `prev@19:00,30` | Comma-separated popup reminders. A number is minutes before the start. `prev@HH:MM` is that time on the day before. `none` disables reminders. Up to 5. |
| `IPO_SHOW_AS` | `free` | `free` or `busy`: whether the event blocks time in your calendar. |

To change the run time, edit the `cron` line in `.github/workflows/sync.yml`. It is in UTC, so `30 16 * * *` is 01:30 JST.

## Running locally

```sh
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q
python -m ipo_sync              # fetch and print only (no credentials set)
```

With `GOOGLE_SERVICE_ACCOUNT_JSON` and `GOOGLE_CALENDAR_ID` set in the environment, `python -m ipo_sync` registers events. `--dry-run` and `--selftest` work as in the workflow.

## Notes

- **Schedule delays**: GitHub may start scheduled runs some minutes late, and may skip the first scheduled run after the workflow is added.
- **Inactive repositories**: GitHub disables scheduled workflows in public repositories after 60 days without activity. Re-enable the workflow in the Actions tab, or keep your copy private.
- **Page changes**: the parser depends on the SBI page layout. If the layout changes, runs fail instead of adding wrong events. Fix `ipo_sync/sbi.py` and the fixture in `tests/`.
- **Scope**: this project only reads a public web page once a day. It never logs in, applies for IPOs or trades. It is not affiliated with SBI Securities, and nothing here is investment advice.

## License

[MIT](LICENSE)
