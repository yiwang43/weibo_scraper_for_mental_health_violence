"""
search_scraper.py
=================
Searches Weibo for each hashtag in the spreadsheet, collects post URLs,
then scrapes comments from any posts not already in the dataset.

USAGE:
  python scripts/search_scraper.py
  python scripts/search_scraper.py --pages 5 --out data/raw/search_comments.json

  --pages  : pages of search results to fetch per hashtag (default: 3, ~10 posts/page)
  --out    : output JSON for newly scraped comments (default: data/raw/search_comments.json)
  --delay  : seconds between requests (default: 3)
"""

import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import requests

BASE = Path(__file__).parent.parent

SEARCH_API = "https://m.weibo.cn/api/container/getIndex"
COMMENT_API      = "https://m.weibo.cn/comments/hotflow"
COMMENT_SHOW_API = "https://m.weibo.cn/api/comments/show"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer":          "https://m.weibo.cn/",
    "Accept":           "application/json, text/plain, */*",
    "Accept-Language":  "zh-CN,zh;q=0.9,en;q=0.8",
    "X-Requested-With": "XMLHttpRequest",
    "MWeibo-Pwa":       "1",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_cookies(path: str) -> dict:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return {c["name"]: c["value"] for c in raw}
    return raw


def normalize_url(url: str) -> str:
    return url.strip().split("?")[0].split("#")[0].rstrip("/")


def extract_post_id(url: str) -> str | None:
    m = re.search(r"(?:detail|status)/([A-Za-z0-9]+)", url)
    if m: return m.group(1)
    m = re.search(r"weibo\.com/\d+/([A-Za-z0-9]+)", url)
    if m: return m.group(1)
    m = re.search(r"weibo\.com/[^/]+/([A-Za-z0-9]{9,})", url)
    if m: return m.group(1)
    return None


def load_existing_urls() -> set[str]:
    """Return normalized URLs already in the dataset."""
    seen = set()
    for json_file in ["data/raw/comments.json", "data/raw/new_comments.json"]:
        p = BASE / json_file
        if not p.exists():
            continue
        for post in json.loads(p.read_text(encoding="utf-8")):
            url = normalize_url(post.get("post_url", ""))
            if url:
                seen.add(url)
    return seen


def load_hashtags() -> list[str]:
    """Extract unique hashtags from the spreadsheet."""
    tags = set()
    csv_path = BASE / "data/raw/Research Data - Sheet1.csv"
    with open(csv_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            raw = row.get("Tag ", "") or row.get("搜索关键词", "")
            for tag in re.findall(r"#([^#\n]+)#", raw):
                tag = tag.strip()
                if tag and len(tag) > 3:   # skip very short tags
                    tags.add(tag)
    return sorted(tags)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def search_hashtag(session: requests.Session, tag: str, pages: int, delay: float) -> list[str]:
    """Return post URLs found under a hashtag search."""
    urls = []
    containerid = f"100808{quote(tag)}"

    for page in range(1, pages + 1):
        params = {
            "containerid": containerid,
            "page_type":   648,
            "page":        page,
        }
        try:
            resp = session.get(SEARCH_API, params=params, timeout=15)
            if not resp.text.strip().startswith("{"):
                break
            data = resp.json()
        except Exception:
            break

        if data.get("ok") != 1:
            break

        cards = data.get("data", {}).get("cards", [])
        for card in cards:
            # cards contain mblog objects
            mblog = card.get("mblog") or {}
            if not mblog:
                # some cards wrap items in a card_group
                for sub in card.get("card_group", []):
                    mblog = sub.get("mblog") or {}
                    if mblog:
                        uid  = mblog.get("user", {}).get("id", "")
                        mid  = mblog.get("bid", "") or mblog.get("id", "")
                        if uid and mid:
                            urls.append(f"https://weibo.com/{uid}/{mid}")
            else:
                uid = mblog.get("user", {}).get("id", "")
                mid = mblog.get("bid", "") or mblog.get("id", "")
                if uid and mid:
                    urls.append(f"https://weibo.com/{uid}/{mid}")

        time.sleep(delay)

    return urls


# ---------------------------------------------------------------------------
# Comment fetching (same two-phase approach as weibo_scraper.py)
# ---------------------------------------------------------------------------

def fetch_post_meta(session, post_id):
    try:
        resp = session.get(f"https://m.weibo.cn/statuses/show?id={post_id}", timeout=15)
        data = resp.json().get("data", {})
        text = data.get("text", "") or ""
        numeric_id = str(data.get("id", "") or data.get("idstr", "") or post_id)
        return text, numeric_id
    except Exception:
        return "", post_id


def parse_comment(c: dict) -> dict:
    user     = c.get("user") or {}
    raw_text = c.get("text", "")
    clean    = re.sub(r"<[^>]+>", "", raw_text).strip()
    reply_user = None
    if c.get("reply_comment"):
        reply_user = (c["reply_comment"].get("user") or {}).get("screen_name")
    return {
        "comment_id":           str(c.get("id", "")),
        "user_id":              str(user.get("id", "")),
        "user_screen_name":     user.get("screen_name", ""),
        "text":                 clean,
        "raw_text":             raw_text,
        "likes":                c.get("like_count") or c.get("like_counts") or 0,
        "created_at":           c.get("created_at", ""),
        "is_reply":             bool(c.get("reply_comment")),
        "reply_to_screen_name": reply_user,
    }


def fetch_comments(session, post_id, max_comments, delay):
    collected, seen_ids = [], set()

    # Phase 1: hotflow page 1
    try:
        resp = session.get(COMMENT_API,
                           params={"id": post_id, "mid": post_id, "max_id_type": 0},
                           timeout=15)
        if resp.status_code == 200 and resp.text.strip():
            payload = resp.json()
            if payload.get("ok") == 1:
                for c in payload.get("data", {}).get("data", []):
                    p = parse_comment(c)
                    if p["comment_id"] not in seen_ids:
                        seen_ids.add(p["comment_id"])
                        collected.append(p)
    except Exception:
        pass
    time.sleep(delay)

    # Phase 2: chronological pages
    page = 1
    while len(collected) < max_comments:
        try:
            resp = session.get(COMMENT_SHOW_API,
                               params={"id": post_id, "page": page},
                               timeout=15)
            if resp.status_code != 200 or not resp.text.strip():
                break
            payload = resp.json()
        except Exception:
            break

        if payload.get("ok") != 1:
            break

        items = payload.get("data", {}).get("data", [])
        if not items:
            break

        for c in items:
            p = parse_comment(c)
            if p["comment_id"] not in seen_ids:
                seen_ids.add(p["comment_id"])
                collected.append(p)
                if len(collected) >= max_comments:
                    break

        page += 1
        time.sleep(delay)

    return collected


def save(results, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pages",  type=int,   default=3)
    parser.add_argument("--max",    type=int,   default=300)
    parser.add_argument("--out",    default=str(BASE / "data/raw/search_comments.json"))
    parser.add_argument("--delay",  type=float, default=3.0)
    args = parser.parse_args()

    cookies = load_cookies(str(BASE / "cookies.json"))
    existing_urls = load_existing_urls()
    hashtags = load_hashtags()

    print(f"Loaded {len(existing_urls)} already-scraped URLs")
    print(f"Found {len(hashtags)} hashtags to search")
    print(f"Fetching {args.pages} pages per hashtag (~{args.pages * 10} posts each)\n")

    session = requests.Session()
    session.headers.update(HEADERS)
    session.cookies.update(cookies)

    # ── Phase 1: collect new URLs via hashtag search ──────────────────────
    all_new_urls: dict[str, str] = {}   # url → tag (for provenance)
    for i, tag in enumerate(hashtags, 1):
        print(f"[{i}/{len(hashtags)}] Searching #{tag}# …", end=" ", flush=True)
        found = search_hashtag(session, tag, args.pages, args.delay)
        new = [normalize_url(u) for u in found if normalize_url(u) not in existing_urls]
        for u in new:
            all_new_urls[u] = tag
        print(f"{len(found)} posts found, {len(new)} new")
        time.sleep(args.delay)

    print(f"\nTotal new URLs to scrape: {len(all_new_urls)}")
    if not all_new_urls:
        print("Nothing new to scrape.")
        return

    # Save the new URL list for reference
    url_list_path = BASE / "data/raw/search_urls.txt"
    with open(url_list_path, "w", encoding="utf-8") as f:
        for url in all_new_urls:
            f.write(url + "\n")
    print(f"Saved new URL list → {url_list_path}")

    # ── Phase 2: scrape comments from new URLs ────────────────────────────
    results = []
    total = len(all_new_urls)

    for i, (url, tag) in enumerate(all_new_urls.items(), 1):
        print(f"\n[{i}/{total}] {url}")
        post_id = extract_post_id(url)
        if not post_id:
            print("    [SKIP] Cannot parse post ID")
            continue

        post_text, numeric_id = fetch_post_meta(session, post_id)
        if numeric_id != post_id:
            print(f"    numeric_id = {numeric_id}")
        time.sleep(args.delay / 2)

        print(f"    Fetching up to {args.max} comments …")
        try:
            comments = fetch_comments(session, numeric_id, args.max, args.delay)
        except Exception as e:
            print(f"    [ERROR] {e}")
            comments = []

        entry = {
            "post_url":           url,
            "post_id":            numeric_id,
            "source_hashtag":     tag,
            "scraped_at":         datetime.now().isoformat(),
            "post_text":          post_text,
            "comments_collected": len(comments),
            "comments":           comments,
            "error":              None,
        }
        results.append(entry)
        print(f"    ✓ {len(comments)} comments")

        save(results, args.out)
        time.sleep(args.delay)

    total_comments = sum(r["comments_collected"] for r in results)
    print(f"\n{'='*50}")
    print(f"Done. {len(results)} new posts → {total_comments:,} comments → {args.out}")
    print(f"Run build_enriched.py to merge into the enriched CSVs.")


if __name__ == "__main__":
    main()
