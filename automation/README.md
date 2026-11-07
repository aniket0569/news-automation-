# Daily front page — how the automation works

Every morning at 09:00 IST, a GitHub Action runs `daily_news.py`, which reads the
RSS feeds of The Hindu and The Indian Express, picks the five most CLAT-relevant
stories, drafts the five items and ten questions, and writes `news/latest.json`.
The website reads that file on load, so the page updates without anyone touching
the HTML.

```
.github/workflows/daily-news.yml   the schedule (03:30 UTC = 09:00 IST)
automation/daily_news.py           fetch → rank → draft → write
data/qbank.json                    the year's question bank, used when no AI key is set
news/latest.json                   what the site reads
news/YYYY-MM-DD.json               a dated copy of each edition
news/archive.json                  headlines only, for an archive page later
```

## Setting it up (about 20 minutes, once)

1. **Put the site in a GitHub repository.** Create a repo, upload the whole folder
   (the site plus `automation/`, `news/`, `data/`, `.github/`), and commit.
2. **Add the AI key.** Repo → *Settings → Secrets and variables → Actions → New
   repository secret*: name `LLM_API_KEY`, value your key. Optionally add
   *Variables* named `LLM_MODEL` (default `gpt-4o-mini`) and `LLM_BASE_URL`
   (default OpenAI; works with any OpenAI-compatible endpoint — Groq, Sarvam,
   OpenRouter, Together).
3. **Turn on Actions.** The *Actions* tab → enable workflows. Run “Daily front
   page” once by hand with *Run workflow* to check it.
4. **Connect the host to the repo.** On Netlify: *Site settings → Build & deploy →
   Link repository*. Then every commit redeploys the site automatically, so the
   morning commit is live within a minute.

Without an AI key the job still runs: the five items are built from the feed
summaries and the ten questions are drawn from `data/qbank.json`. It is weaker,
but nothing breaks.

## What it can and cannot do

- **It reads feeds, not articles.** RSS gives the headline and a short summary.
  The AI writes the “catch” line from that summary and is instructed not to
  invent facts. If you want fuller summaries, the honest route is a paid news API
  (NewsAPI, GNews) whose terms allow it.
- **Paywalls stay respected.** Nothing is scraped from behind a paywall, and the
  site shows only a short summary plus a link to the source.
- **Attribution is in the page.** Each item carries its paper's name; keep it.
- **Cost.** GitHub Actions is free for public repos and includes 2,000 minutes a
  month for private ones — this job uses about one minute a day. An AI call of
  this size costs well under a rupee.
- **It fails quietly by design.** If the feeds are unreachable, the script exits
  without writing, and yesterday's edition stays live rather than blanking.

## Changing it

- **Different papers or sections:** edit `FEEDS` at the top of `daily_news.py`.
- **What counts as important:** edit `RULES` — each pattern carries a weight and
  the “why it matters” line it produces.
- **Different time:** change the cron line. IST is UTC+5:30, so 09:00 IST is
  `30 3 * * *`. GitHub sometimes runs scheduled jobs a few minutes late under load.
- **Test locally:** `python automation/daily_news.py --selftest` parses a built-in
  fixture without touching the network.
