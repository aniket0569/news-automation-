#!/usr/bin/env python3
"""
CLAT: Final Round — daily front page builder.

Runs each morning, pulls the RSS feeds of The Hindu and The Indian Express,
picks the five stories most useful for CLAT, writes the five items and ten
questions, and saves them as news/latest.json (plus a dated copy and an archive).

Two modes:
  * With an LLM key set, the five "catch" lines, the "why it matters" lines and
    the ten questions are written by the model from the headlines and summaries.
  * Without a key, it still runs: the items are built from the feed summaries
    and the ten questions are sampled from the year's question bank.

Usage:
  python automation/daily_news.py              # normal run
  python automation/daily_news.py --selftest   # parse a built-in fixture, no network
"""

import json
import os
import re
import sys
import html
import hashlib
import datetime
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NEWS_DIR = ROOT / "news"
BANK_PATH = ROOT / "data" / "qbank.json"

# --------------------------------------------------------------------------- feeds
# weight: how much a section matters for CLAT
FEEDS = [
    {"name": "The Hindu", "url": "https://www.thehindu.com/news/national/feeder/default.rss", "weight": 5},
    {"name": "The Hindu", "url": "https://www.thehindu.com/news/international/feeder/default.rss", "weight": 3},
    {"name": "The Hindu", "url": "https://www.thehindu.com/business/feeder/default.rss", "weight": 4},
    {"name": "The Hindu", "url": "https://www.thehindu.com/sci-tech/feeder/default.rss", "weight": 3},
    {"name": "Indian Express", "url": "https://indianexpress.com/section/india/feed/", "weight": 5},
    {"name": "Indian Express", "url": "https://indianexpress.com/section/explained/feed/", "weight": 5},
    {"name": "Indian Express", "url": "https://indianexpress.com/section/business/feed/", "weight": 4},
]

# keywords that make a story CLAT-worthy, with the exam angle they point to
RULES = [
    (r"supreme court|high court|constitution bench|article \d+|judgment|verdict|chief justice",
     6, "Constitutional law: which Article, which court, and what the ruling changes."),
    (r"parliament|bill|ordinance|lok sabha|rajya sabha|amendment act",
     5, "How a law is made, and which list or Article it draws its power from."),
    (r"rbi|repo rate|monetary policy|inflation|gst|budget|fiscal deficit|rupee|sebi|npa",
     5, "Economy: the policy instrument, the body that sets it, and the direction of the number."),
    (r"scheme|yojana|mission|cabinet approves|subsidy|beneficiar",
     5, "A welfare scheme: who funds it, who delivers it, and the eligibility line."),
    (r"election commission|election|electoral|voter|by-election|assembly poll",
     4, "The electoral machinery: who conducts it, and under which power."),
    (r"census|registrar general|population|survey",
     4, "Governance data: which body collects it, and under which statute."),
    (r"missile|drdo|army|navy|air force|defence|exercise|agniveer|indigenous",
     3, "Defence: the platform, the agency that built it, and what it replaces."),
    (r"isro|space|satellite|launch vehicle|gaganyaan|chandrayaan",
     3, "Space: the vehicle, the orbit, and the agency."),
    (r"climate|cop\d*|emission|pollution|aqi|biodiversity|ramsar|wildlife",
     3, "Environment: the treaty, the standard, or the authority that enforces it."),
    (r"unesco|heritage|gi tag|award|nobel|padma|bharat ratna|honour",
     2, "Culture and honours: the body that confers it, and the year."),
    (r"treaty|summit|brics|g20|united nations|wto|imf|world bank|sanction",
     4, "International law and institutions: membership, mandate, and obligation."),
    (r"olympic|asian games|world cup|medal|championship|cricket|hockey",
     2, "Sport: the event, the format, and the body that runs it."),
]

FALLBACK_ANGLES = [
    "Read it for the institution involved: who decided, under which power, and who is bound.",
    "Ask what changed in the rule, not what happened on the day.",
    "Note the numbers, and note who produced them.",
]

UA = "Mozilla/5.0 (compatible; CLATFinalRoundBot/1.0; +https://clatfinalround.in)"


# --------------------------------------------------------------------------- helpers
def clean(text, limit=340):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        cut = text[:limit].rsplit(" ", 1)[0]
        text = cut.rstrip(",.;:") + "…"
    return text


def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/xml"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def parse_feed(raw, source, weight):
    """Accepts RSS 2.0 or Atom and returns a list of story dicts."""
    items = []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return items
    ns = {"a": "http://www.w3.org/2005/Atom"}

    for it in root.iter():
        tag = it.tag.split("}")[-1]
        if tag not in ("item", "entry"):
            continue
        title = link = desc = pub = ""
        for child in it:
            t = child.tag.split("}")[-1]
            if t == "title":
                title = clean(child.text or "", 220)
            elif t == "link":
                link = (child.text or "").strip() or child.attrib.get("href", "")
            elif t in ("description", "summary", "content"):
                if not desc:
                    desc = clean(child.text or "")
            elif t in ("pubDate", "published", "updated"):
                pub = (child.text or "").strip()
        if title and link:
            items.append({"title": title, "link": link, "desc": desc, "pub": pub,
                          "src": source, "weight": weight})
    return items


def parse_date(s):
    if not s:
        return None
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
                "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.datetime.strptime(s.strip(), fmt)
        except ValueError:
            continue
    return None


def score(item, now):
    text = (item["title"] + " " + item["desc"]).lower()
    s = item["weight"]
    angle = None
    for pattern, points, why in RULES:
        if re.search(pattern, text):
            s += points
            if angle is None:
                angle = why
    dt = parse_date(item["pub"])
    if dt:
        try:
            age = (now - dt.replace(tzinfo=None)).total_seconds() / 3600
        except (TypeError, ValueError):
            age = 24
        if age <= 12:
            s += 3
        elif age <= 24:
            s += 1
        else:
            s -= 2
    item["score"] = s
    item["angle"] = angle or FALLBACK_ANGLES[hash(item["title"]) % len(FALLBACK_ANGLES)]
    return s


def similar(a, b):
    ta = set(re.findall(r"[a-z]{4,}", a.lower()))
    tb = set(re.findall(r"[a-z]{4,}", b.lower()))
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) > 0.55


def pick_five(items):
    chosen = []
    for it in sorted(items, key=lambda x: -x["score"]):
        if any(similar(it["title"], c["title"]) for c in chosen):
            continue
        # keep both papers represented: at most three from one source
        if sum(1 for c in chosen if c["src"] == it["src"]) >= 3:
            continue
        chosen.append(it)
        if len(chosen) == 5:
            break
    return chosen


# --------------------------------------------------------------------------- LLM drafting
def llm_draft(five, api_key, model, base_url):
    """Ask a chat model for the five items and ten questions, as strict JSON."""
    stories = [{"headline": f["title"], "summary": f["desc"], "source": f["src"]} for f in five]
    prompt = (
        "You are writing a daily current-affairs page for Indian law-entrance students (CLAT).\n"
        "Below are five news stories with headlines and short summaries.\n\n"
        + json.dumps(stories, ensure_ascii=False, indent=1)
        + """

Return ONLY JSON, no prose, in this exact shape:
{"news":[{"h":"headline in plain words","catch":"2-3 sentences saying what actually happened, factual, no hype","why":"one line naming the exam angle (Article, statute, institution, scheme, treaty)","src":"source name"}],
 "quiz":[{"q":"question","o":["opt","opt","opt","opt"],"a":0,"e":"one-line explanation"}]}

Rules:
- Exactly 5 news items and exactly 10 quiz questions.
- The 10 questions must be answerable ONLY from the five items above, mixed with static knowledge a CLAT student should know (Articles, institutions, years).
- Options must be short, similar in length, and no option may be eliminable just because it sounds extreme.
- "a" is the index (0-3) of the correct option.
- Never invent a fact that is not in the summaries or settled static knowledge. If a summary is thin, keep the catch short rather than guessing.
"""
    )
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.4,
        "response_format": {"type": "json_object"},
    }).encode()

    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + api_key},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        body = json.loads(r.read())
    content = body["choices"][0]["message"]["content"]
    content = re.sub(r"^```(json)?|```$", "", content.strip(), flags=re.M).strip()
    data = json.loads(content)

    if len(data.get("news", [])) < 5 or len(data.get("quiz", [])) < 10:
        raise ValueError("model returned too few items")
    for q in data["quiz"][:10]:
        if len(q.get("o", [])) != 4 or not (0 <= int(q.get("a", -1)) <= 3):
            raise ValueError("malformed question")
    return data["news"][:5], data["quiz"][:10]


def bank_quiz(five):
    """Fallback: ten questions from the year's bank, matched to today's themes."""
    if not BANK_PATH.exists():
        return []
    bank = json.loads(BANK_PATH.read_text())
    words = " ".join(f["title"] + " " + f["desc"] for f in five).lower()
    scored = []
    for q in bank:
        theme = q.get("t", "").lower()
        hits = sum(1 for w in re.findall(r"[a-z]{5,}", theme) if w in words)
        scored.append((hits, q))
    scored.sort(key=lambda x: -x[0])
    picked = [q for _, q in scored[:10]]
    return [{"q": q["q"], "o": q["o"], "a": q["a"], "e": q["e"]} for q in picked]


# --------------------------------------------------------------------------- build
def build(five, news_items, quiz, today):
    return {
        "date": today.isoformat(),
        "label": today.strftime("%A, %-d %B %Y") if os.name != "nt" else today.strftime("%A, %d %B %Y"),
        "sources": " · ".join(sorted({f["src"] for f in five})),
        "news": news_items,
        "quiz": quiz,
    }


def fallback_items(five):
    out = []
    for f in five:
        out.append({
            "h": f["title"],
            "catch": f["desc"] or f["title"],
            "why": f["angle"],
            "src": f["src"],
            "url": f["link"],
        })
    return out


def save(edition, today):
    NEWS_DIR.mkdir(exist_ok=True)
    (NEWS_DIR / "latest.json").write_text(json.dumps(edition, ensure_ascii=False, indent=1))
    (NEWS_DIR / f"{today.isoformat()}.json").write_text(json.dumps(edition, ensure_ascii=False, indent=1))
    archive_path = NEWS_DIR / "archive.json"
    archive = []
    if archive_path.exists():
        try:
            archive = json.loads(archive_path.read_text())
        except json.JSONDecodeError:
            archive = []
    archive = [a for a in archive if a.get("date") != edition["date"]]
    archive.insert(0, {"date": edition["date"], "label": edition["label"],
                       "headlines": [n["h"] for n in edition["news"]]})
    (archive_path).write_text(json.dumps(archive[:120], ensure_ascii=False, indent=1))
    print(f"wrote news/latest.json for {edition['date']} with {len(edition['news'])} items, {len(edition['quiz'])} questions")


def main():
    today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
    now = today.replace(tzinfo=None)

    if "--selftest" in sys.argv:
        raw = b"""<?xml version="1.0"?><rss><channel>
        <item><title>Supreme Court holds 24-hour rule mandatory</title><description>&lt;p&gt;The Court said detention beyond a day without a magistrate breaches Article 22(2).&lt;/p&gt;</description><link>https://example.org/a</link><pubDate>Thu, 05 Nov 2026 20:00:00 +0530</pubDate></item>
        <item><title>Cabinet approves new rural scheme</title><description>A centrally sponsored scheme for 2026-31.</description><link>https://example.org/b</link><pubDate>Thu, 05 Nov 2026 18:00:00 +0530</pubDate></item>
        </channel></rss>"""
        items = parse_feed(raw, "The Hindu", 5)
        for it in items:
            score(it, now)
        print("selftest parsed:", [(i["title"], i["score"], i["angle"][:40]) for i in items])
        return

    items = []
    for feed in FEEDS:
        try:
            raw = fetch(feed["url"])
            got = parse_feed(raw, feed["name"], feed["weight"])
            items.extend(got)
            print(f"{feed['name']:16s} {len(got):3d} items  {feed['url']}")
        except Exception as e:
            print(f"feed failed: {feed['url']} ({e})")

    if not items:
        print("no stories fetched; leaving yesterday's edition in place")
        sys.exit(0)

    for it in items:
        score(it, now)
    five = pick_five(items)
    print("chosen:", [f["title"][:60] for f in five])

    key = os.environ.get("LLM_API_KEY", "").strip()
    model = os.environ.get("LLM_MODEL", "gpt-4o-mini").strip()
    base = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").strip()

    news_items, quiz = None, None
    if key:
        try:
            news_items, quiz = llm_draft(five, key, model, base)
            print("drafted with the model")
        except Exception as e:
            print("model draft failed, falling back:", e)

    if not news_items:
        news_items = fallback_items(five)
    if not quiz:
        quiz = bank_quiz(five)
        print("questions taken from the year's bank")

    save(build(five, news_items, quiz, today), today)


if __name__ == "__main__":
    main()
