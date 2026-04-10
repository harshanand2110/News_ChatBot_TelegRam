import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timezone

import feedparser
import requests



BOT_TOKEN = "Use Bot TOKEN here"       # From @BotFather
CHAT_ID   = "Use Chat ID"        # Your chat/group ID
NEWS_API_KEY = ""                            # Optional – newsapi.org key

# Topics to track (used for NewsAPI keyword search)
TOPICS = [
    "stock market",
    "Sensex",
    "Nifty",
    "RBI interest rate",
    "cryptocurrency",
]

# RSS feeds to monitor (always active, no API key needed)
RSS_FEEDS = [
    
    "https://feeds.feedburner.com/ndtvprofit-latest",
    "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "https://www.moneycontrol.com/rss/MCtopnews.xml",
    "https://feeds.reuters.com/reuters/businessNews",
    "https://feeds.bbci.co.uk/news/business/rss.xml",

    "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
    "https://www.thehindu.com/business/Economy/feeder/default.rss",
]

# How many articles to send per run (per source)
MAX_ARTICLES_PER_FEED   = 3
MAX_ARTICLES_FROM_API   = 5

# File to track already-sent articles (avoids duplicates)
SEEN_CACHE_FILE = "seen_articles.json"

# ─────────────────────────────────────────────
# INTERNALS — no need to edit below
# ─────────────────────────────────────────────

def load_seen() -> set:
    if os.path.exists(SEEN_CACHE_FILE):
        with open(SEEN_CACHE_FILE) as f:
            return set(json.load(f))
    return set()

def save_seen(seen: set):
    with open(SEEN_CACHE_FILE, "w") as f:
        json.dump(list(seen), f)

def article_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()

def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            print(f"    Telegram error {r.status_code}: {r.text}")
        else:
            print("   Sent to Telegram")
    except Exception as e:
        print(f"   Failed to send: {e}")

def format_article(title: str, link: str, source: str, published: str = "") -> str:
    pub = f"\n🕐 {published}" if published else ""
    return (
        f"📰 <b>{title}</b>\n"
        f"🔗 <a href='{link}'>Read full article</a>\n"
        f"📡 Source: {source}{pub}"
    )

def fetch_rss_articles(seen: set) -> list[dict]:
    articles = []
    for feed_url in RSS_FEEDS:
        try:
            print(f"  📡 Fetching RSS: {feed_url}")
            feed = feedparser.parse(feed_url)
            source_name = feed.feed.get("title", feed_url)
            count = 0
            for entry in feed.entries:
                if count >= MAX_ARTICLES_PER_FEED:
                    break
                link = entry.get("link", "")
                uid = article_id(link)
                if uid in seen:
                    continue
                title = entry.get("title", "No title")
                published = entry.get("published", "")
                articles.append({
                    "uid": uid,
                    "title": title,
                    "link": link,
                    "source": source_name,
                    "published": published,
                })
                count += 1
        except Exception as e:
            print(f"    RSS error for {feed_url}: {e}")
    return articles

def fetch_newsapi_articles(seen: set) -> list[dict]:
    if not NEWS_API_KEY:
        return []
    articles = []
    query = " OR ".join(TOPICS)
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": query,
        "sortBy": "publishedAt",
        "pageSize": MAX_ARTICLES_FROM_API,
        "language": "en",
        "apiKey": NEWS_API_KEY,
    }
    try:
        print(f"   Fetching from NewsAPI for: {query[:60]}...")
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        for art in data.get("articles", []):
            link = art.get("url", "")
            uid = article_id(link)
            if uid in seen:
                continue
            articles.append({
                "uid": uid,
                "title": art.get("title", "No title"),
                "link": link,
                "source": art.get("source", {}).get("name", "NewsAPI"),
                "published": art.get("publishedAt", "")[:10],
            })
    except Exception as e:
        print(f"    NewsAPI error: {e}")
    return articles

def run_once():
    print(f"\n{'='*50}")
    print(f"   Running at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*50}")

    seen = load_seen()
    all_articles = []

    # Gather from RSS feeds
    all_articles += fetch_rss_articles(seen)

    # Gather from NewsAPI (if key provided)
    all_articles += fetch_newsapi_articles(seen)

    if not all_articles:
        print("  ℹ  No new articles found.")
        return

    print(f"\n   Sending {len(all_articles)} new article(s) to Telegram...\n")

    # Send header
    now_str = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    send_telegram(
        f"🗞 <b>News Update</b> — {now_str}\n"
        f"Topics: {', '.join(TOPICS)}\n"
        f"━━━━━━━━━━━━━━━━━━━━━"
    )
    time.sleep(0.5)

    new_seen = set()
    for art in all_articles:
        msg = format_article(art["title"], art["link"], art["source"], art["published"])
        send_telegram(msg)
        new_seen.add(art["uid"])
        time.sleep(0.3)   # slight delay to avoid Telegram rate limits

    seen.update(new_seen)
    save_seen(seen)
    print(f"\n   Done. {len(new_seen)} article(s) sent and cached.")

def main():
    parser = argparse.ArgumentParser(description="Telegram News Bot")
    parser.add_argument("--loop", action="store_true",
                        help="Keep running on a schedule")
    parser.add_argument("--interval", type=int, default=30,
                        help="Interval in minutes between updates (default: 30)")
    args = parser.parse_args()

    # Validate config
    if BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN" or CHAT_ID == "YOUR_TELEGRAM_CHAT_ID":
        print(" Please set BOT_TOKEN and CHAT_ID in the script before running.")
        return

    if args.loop:
        print(f"⏰ Running in loop mode every {args.interval} minute(s). Press Ctrl+C to stop.")
        while True:
            run_once()
            print(f"\n   Sleeping {args.interval} min...\n")
            time.sleep(args.interval * 60)
    else:
        run_once()

if __name__ == "__main__":
    main()
