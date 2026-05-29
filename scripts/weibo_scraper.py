"""
weibo_scraper.py
================
Pulls comment threads from a list of Weibo post URLs for research purposes.
Authentication via browser-exported cookies (no Selenium needed).

SETUP (one-time):
  1. Install the "EditThisCookie" Chrome extension (or "Cookie-Editor" for Firefox).
  2. Log into weibo.com in your browser.
  3. Click the extension → Export → copy the JSON.
  4. Paste into a file called  cookies.json  in the same folder as this script.

USAGE:
  python weibo_scraper.py --urls urls.txt --out comments.json --max 300

  --urls   : text file with one Weibo post URL per line (copy from your spreadsheet)
  --out    : output JSON file path  (default: weibo_comments.json)
  --max    : max comments to collect per post  (default: 300)
  --delay  : seconds to wait between requests  (default: 2.5)
  --cookies: path to cookies JSON file  (default: cookies.json)

OUTPUT FORMAT (one entry per post):
  {
    "post_url": "https://weibo.com/...",
    "post_id": "...",
    "scraped_at": "2025-...",
    "post_text": "...",
    "comments": [
      {
        "comment_id": "...",
        "user_id": "...",
        "user_screen_name": "...",
        "text": "...",
        "likes": 123,
        "created_at": "...",
        "is_reply": false,
        "reply_to_screen_name": null
      },
      ...
    ],
    "comments_collected": 300,
    "error": null   // populated if scraping failed for this post
  }
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests


# ---------------------------------------------------------------------------
# Weibo API endpoints
# ---------------------------------------------------------------------------
# Weibo's mobile API is more stable and less rate-limited than the desktop one.
COMMENT_API      = "https://m.weibo.cn/comments/hotflow"
COMMENT_SHOW_API = "https://m.weibo.cn/api/comments/show"
POST_API         = "https://m.weibo.cn/detail/{post_id}"
POST_API2        = "https://m.weibo.cn/statuses/show?id={post_id}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://m.weibo.cn/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "X-Requested-With": "XMLHttpRequest",
    "MWeibo-Pwa": "1",
}


# ---------------------------------------------------------------------------
# Cookie handling
# ---------------------------------------------------------------------------

def load_cookies(cookie_path: str) -> dict:
    """
    Parse cookies exported by EditThisCookie (list of dicts with 'name'/'value')
    OR a simple Netscape/key=value string format.
    Returns a plain {name: value} dict for requests.
    """
    path = Path(cookie_path)
    if not path.exists():
        print(f"[ERROR] Cookie file not found: {cookie_path}")
        print(
            "  → Log into weibo.com, export cookies via EditThisCookie,\n"
            "    and save the JSON as 'cookies.json' next to this script."
        )
        sys.exit(1)

    raw = path.read_text(encoding="utf-8").strip()

    # EditThisCookie format: list of dicts
    if raw.startswith("["):
        cookie_list = json.loads(raw)
        return {c["name"]: c["value"] for c in cookie_list}

    # Simple key=value; separated string (copy from browser DevTools)
    cookies = {}
    for part in raw.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            cookies[k.strip()] = v.strip()
    return cookies


# ---------------------------------------------------------------------------
# URL → post ID
# ---------------------------------------------------------------------------

def extract_post_id(url: str) -> str | None:
    """
    Handles all common Weibo URL formats:
      https://weibo.com/1234567/AbCdEfG
      https://m.weibo.cn/detail/1234567890123456
      https://m.weibo.cn/status/1234567890123456
      https://weibo.com/u/1234567?type=...
    Returns the alphanumeric post ID string or None if unrecognised.
    """
    url = url.strip()

    # m.weibo.cn/detail/<id>  or  /status/<id>
    m = re.search(r"(?:detail|status)/([A-Za-z0-9]+)", url)
    if m:
        return m.group(1)

    # weibo.com/<uid>/<mid>  — the short base62 mid at the end
    m = re.search(r"weibo\.com/\d+/([A-Za-z0-9]+)", url)
    if m:
        return m.group(1)

    # weibo.com/<screenname>/<mid>
    m = re.search(r"weibo\.com/[^/]+/([A-Za-z0-9]{9,})", url)
    if m:
        return m.group(1)

    return None


# ---------------------------------------------------------------------------
# Fetch post text
# ---------------------------------------------------------------------------

def fetch_post_meta(session: requests.Session, post_id: str) -> tuple[str, str]:
    """
    Returns (post_text, numeric_id).
    numeric_id is the long integer ID Weibo uses internally — needed for
    stable comment pagination when the input post_id is a base62 short ID.
    """
    try:
        url = POST_API2.format(post_id=post_id)
        resp = session.get(url, timeout=15)
        data = resp.json().get("data", {})
        text = data.get("text", "") or ""
        numeric_id = str(data.get("id", "") or data.get("idstr", "") or post_id)
        return text, numeric_id
    except Exception:
        return "", post_id


# ---------------------------------------------------------------------------
# Fetch comments (paginated)
# ---------------------------------------------------------------------------

def fetch_comments(
    session: requests.Session,
    post_id: str,
    max_comments: int,
    delay: float,
    post_url: str = "",
) -> list[dict]:
    """
    Two-phase collection:
      Phase 1 — hotflow page 1: top-engagement comments (most liked).
      Phase 2 — /api/comments/show (page-based): chronological volume.
    Deduplicates across both sources by comment_id.
    """
    collected: list[dict] = []
    seen_ids: set[str] = set()

    # ── Phase 1: hotflow page 1 (top-liked comments) ───────────────────────
    try:
        resp = session.get(
            COMMENT_API,
            params={"id": post_id, "mid": post_id, "max_id_type": 0},
            timeout=15,
        )
        if resp.status_code == 200 and resp.text.strip():
            payload = resp.json()
            if payload.get("ok") == 1:
                for c in payload.get("data", {}).get("data", []):
                    parsed = _parse_comment(c)
                    if parsed["comment_id"] not in seen_ids:
                        seen_ids.add(parsed["comment_id"])
                        collected.append(parsed)
    except Exception:
        pass
    time.sleep(delay)

    # ── Phase 2: chronological via /api/comments/show ───────────────────────
    page = 1
    while len(collected) < max_comments:
        try:
            resp = session.get(
                COMMENT_SHOW_API,
                params={"id": post_id, "page": page},
                timeout=15,
            )
        except requests.RequestException as e:
            print(f"    [WARN] Request error: {e}")
            break

        if resp.status_code == 418:
            print("    [WARN] Got 418 — Weibo is blocking. Try refreshing cookies.")
            break
        if resp.status_code != 200 or not resp.text.strip():
            break

        try:
            payload = resp.json()
        except Exception:
            break

        if payload.get("ok") != 1:
            if not collected:
                print(f"    [INFO] API ok=0, no comments (post removed or locked)")
            break

        items = payload.get("data", {}).get("data", [])
        if not items:
            break

        for c in items:
            parsed = _parse_comment(c)
            if parsed["comment_id"] not in seen_ids:
                seen_ids.add(parsed["comment_id"])
                collected.append(parsed)
                if len(collected) >= max_comments:
                    break

        page += 1
        time.sleep(delay)

    return collected


def _parse_comment(c: dict) -> dict:
    """Extract the fields we care about from a raw comment object."""
    user        = c.get("user") or {}
    reply_to    = c.get("reply_original_text") or None
    reply_user  = None
    if c.get("reply_comment"):
        reply_user = (c["reply_comment"].get("user") or {}).get("screen_name")

    # Strip HTML tags from comment text
    raw_text = c.get("text", "")
    clean_text = re.sub(r"<[^>]+>", "", raw_text).strip()

    return {
        "comment_id":           str(c.get("id", "")),
        "user_id":              str(user.get("id", "")),
        "user_screen_name":     user.get("screen_name", ""),
        "text":                 clean_text,
        "raw_text":             raw_text,          # keep original with emoji/links
        "likes":                c.get("like_count") or c.get("like_counts") or 0,
        "created_at":           c.get("created_at", ""),
        "is_reply":             bool(c.get("reply_comment")),
        "reply_to_screen_name": reply_user,
        "reply_to_text":        reply_to,
    }


# ---------------------------------------------------------------------------
# Main scraping loop
# ---------------------------------------------------------------------------

def scrape_urls(
    urls: list[str],
    cookies: dict,
    max_comments: int,
    delay: float,
    out_path: str,
) -> None:
    session = requests.Session()
    session.headers.update(HEADERS)
    session.cookies.update(cookies)

    results = []
    total   = len(urls)

    for i, url in enumerate(urls, 1):
        url = url.strip()
        if not url or url.startswith("#"):
            continue

        print(f"\n[{i}/{total}] {url}")
        post_id = extract_post_id(url)

        if not post_id:
            print("    [SKIP] Could not parse post ID from URL")
            results.append({
                "post_url": url,
                "post_id":  None,
                "error":    "Could not parse post ID",
            })
            continue

        print(f"    post_id = {post_id}")

        # Fetch post text + resolve numeric ID for stable pagination
        post_text, numeric_id = fetch_post_meta(session, post_id)
        if numeric_id != post_id:
            print(f"    numeric_id = {numeric_id}")
        time.sleep(delay / 2)

        # Fetch comments
        print(f"    Fetching up to {max_comments} comments …")
        try:
            comments = fetch_comments(session, numeric_id, max_comments, delay, post_url=url)
        except Exception as e:
            print(f"    [ERROR] {e}")
            results.append({
                "post_url":  url,
                "post_id":   post_id,
                "scraped_at": datetime.now().isoformat(),
                "error":     str(e),
                "comments":  [],
            })
            continue

        entry = {
            "post_url":           url,
            "post_id":            post_id,
            "scraped_at":         datetime.now().isoformat(),
            "post_text":          post_text,
            "comments_collected": len(comments),
            "comments":           comments,
            "error":              None,
        }
        results.append(entry)
        print(f"    ✓ {len(comments)} comments collected")

        # Save incrementally so partial results aren't lost on interrupt
        _save(results, out_path)
        time.sleep(delay)

    print(f"\n{'='*50}")
    print(f"Done. {len(results)} posts processed → {out_path}")


def _save(results: list, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Scrape Weibo comment threads for research."
    )
    parser.add_argument(
        "--urls",
        default="urls.txt",
        help="Text file with one Weibo post URL per line (default: urls.txt)",
    )
    parser.add_argument(
        "--out",
        default="weibo_comments.json",
        help="Output JSON file (default: weibo_comments.json)",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=300,
        help="Max comments per post (default: 300)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.5,
        help="Seconds between requests (default: 2.5 — don't go lower)",
    )
    parser.add_argument(
        "--cookies",
        default="cookies.json",
        help="Path to cookies JSON exported from EditThisCookie (default: cookies.json)",
    )
    args = parser.parse_args()

    print("Weibo Comment Scraper — Research Use")
    print("=" * 50)

    cookies = load_cookies(args.cookies)
    print(f"Loaded {len(cookies)} cookies from {args.cookies}")

    url_path = Path(args.urls)
    if not url_path.exists():
        print(f"[ERROR] URL file not found: {args.urls}")
        print("  → Create a text file with one Weibo URL per line.")
        sys.exit(1)

    urls = [u for u in url_path.read_text(encoding="utf-8").splitlines() if u.strip()]
    print(f"Loaded {len(urls)} URLs from {args.urls}")
    print(f"Max comments per post: {args.max}")
    print(f"Delay between requests: {args.delay}s")

    scrape_urls(
        urls=urls,
        cookies=cookies,
        max_comments=args.max,
        out_path=args.out,
        delay=args.delay,
    )


if __name__ == "__main__":
    main()
