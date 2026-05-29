"""
playwright_deep_scraper.py
==========================
Uses a real browser (Playwright) to collect deep comment threads from
high-comment Weibo posts. Bypasses the 2-page API limit by running
requests inside an authenticated browser context.

USAGE:
  python playwright_deep_scraper.py --max 1000
  python playwright_deep_scraper.py --max 1000 --out deep_comments.json

  --max      : max comments per post (default: 1000)
  --min-post : only scrape posts with declared comment count >= N (default: 1000)
  --out      : output file (default: deep_comments.json)
  --delay    : seconds between page requests (default: 2.0)
"""

import argparse
import asyncio
import csv
import json
import re
import time
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

COMMENT_SHOW_API = "https://m.weibo.cn/api/comments/show"
COMMENT_API      = "https://m.weibo.cn/comments/hotflow"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_url(url: str) -> str:
    return url.strip().split("?")[0].split("#")[0].rstrip("/")


def load_cookies(path: str) -> list[dict]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    # Convert EditThisCookie format → Playwright format
    pw_cookies = []
    for c in raw:
        domain = c.get("domain", "")
        # Playwright needs domain without leading dot for hostOnly cookies
        if c.get("hostOnly") and domain.startswith("."):
            domain = domain[1:]
        pw_cookies.append({
            "name":     c["name"],
            "value":    c["value"],
            "domain":   domain,
            "path":     c.get("path", "/"),
            "secure":   c.get("secure", False),
            "httpOnly": c.get("httpOnly", False),
            "sameSite": "None",
        })
    return pw_cookies


def parse_declared_comments(s: str) -> int:
    m = re.search(r"([\d.]+)([万千]?)评", s.strip())
    if not m:
        return 0
    n = float(m.group(1))
    if m.group(2) == "万":
        n *= 10000
    elif m.group(2) == "千":
        n *= 1000
    return int(n)


def parse_comment(c: dict) -> dict:
    user = c.get("user") or {}
    raw_text = c.get("text", "")
    clean_text = re.sub(r"<[^>]+>", "", raw_text).strip()
    reply_user = None
    if c.get("reply_comment"):
        reply_user = (c["reply_comment"].get("user") or {}).get("screen_name")
    return {
        "comment_id":           str(c.get("id", "")),
        "user_id":              str(user.get("id", "")),
        "user_screen_name":     user.get("screen_name", ""),
        "text":                 clean_text,
        "likes":                c.get("like_count") or c.get("like_counts") or 0,
        "created_at":           c.get("created_at", ""),
        "is_reply":             bool(c.get("reply_comment")),
        "reply_to_screen_name": reply_user,
    }


def save(results: list, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Identify target posts
# ---------------------------------------------------------------------------

def get_target_posts(spreadsheet: str, min_comments: int) -> list[dict]:
    """Return posts from spreadsheet with declared comment count >= min_comments."""
    with open(spreadsheet, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    last_incident = ""
    for r in rows:
        if r.get("事件 incident", "").strip():
            last_incident = r["事件 incident"].strip()
        r["incident"] = last_incident

    targets = []
    seen_urls = set()
    for r in rows:
        url = normalize_url(r.get("URL", ""))
        if not url or url in seen_urls:
            continue
        n = parse_declared_comments(r.get("转赞评 ", ""))
        if n >= min_comments:
            seen_urls.add(url)
            targets.append({
                "url":              url,
                "incident":         r["incident"],
                "title":            r.get("标题", ""),
                "declared_comments": n,
            })

    targets.sort(key=lambda x: -x["declared_comments"])
    return targets


# ---------------------------------------------------------------------------
# Per-post scraping (runs inside the browser)
# ---------------------------------------------------------------------------

async def fetch_comments_browser(page, post_id: str, max_comments: int, delay: float) -> list[dict]:
    """
    Fetches comments using the browser's own fetch() — authenticated,
    bot-detection already passed by visiting the post page.
    """
    collected = []
    seen_ids: set[str] = set()

    # Phase 1: hotflow page 1 (top-liked comments)
    hotflow_js = f"""
    async () => {{
        const r = await fetch(
            'https://m.weibo.cn/comments/hotflow?id={post_id}&mid={post_id}&max_id_type=0',
            {{credentials: 'include', headers: {{'X-Requested-With': 'XMLHttpRequest', 'MWeibo-Pwa': '1'}}}}
        );
        return await r.json();
    }}
    """
    try:
        payload = await page.evaluate(hotflow_js)
        if payload.get("ok") == 1:
            for c in payload.get("data", {}).get("data", []):
                parsed = parse_comment(c)
                if parsed["comment_id"] not in seen_ids:
                    seen_ids.add(parsed["comment_id"])
                    collected.append(parsed)
    except Exception:
        pass

    await asyncio.sleep(delay)

    # Phase 2: chronological pages via /api/comments/show
    page_num = 1
    while len(collected) < max_comments:
        show_js = f"""
        async () => {{
            const r = await fetch(
                'https://m.weibo.cn/api/comments/show?id={post_id}&page={page_num}',
                {{credentials: 'include', headers: {{'X-Requested-With': 'XMLHttpRequest', 'MWeibo-Pwa': '1'}}}}
            );
            const text = await r.text();
            if (!text || !text.trim().startsWith('{{')) return null;
            return JSON.parse(text);
        }}
        """
        try:
            payload = await page.evaluate(show_js)
        except Exception:
            break

        if not payload or payload.get("ok") != 1:
            break

        items = payload.get("data", {}).get("data", [])
        if not items:
            break

        for c in items:
            parsed = parse_comment(c)
            if parsed["comment_id"] not in seen_ids:
                seen_ids.add(parsed["comment_id"])
                collected.append(parsed)
                if len(collected) >= max_comments:
                    break

        page_num += 1
        await asyncio.sleep(delay)

    return collected


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run(args):
    targets = get_target_posts("Research Data - Sheet1.csv", args.min_post)
    print(f"Found {len(targets)} posts with {args.min_post:,}+ declared comments")
    for t in targets:
        print(f"  {t['declared_comments']:>9,}  {t['incident'][:35]:<35}  {t['url']}")
    print()

    cookies = load_cookies("cookies.json")
    out_path = args.out
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="zh-CN",
            viewport={"width": 390, "height": 844},
        )
        await context.add_cookies(cookies)
        page = await context.new_page()

        total = len(targets)
        for i, target in enumerate(targets, 1):
            url = target["url"]
            print(f"\n[{i}/{total}] {url}")
            print(f"    incident: {target['incident']}")
            print(f"    declared: {target['declared_comments']:,} comments")

            # Extract post_id from URL
            m = re.search(r"(?:detail|status)/([A-Za-z0-9]+)", url)
            if not m:
                m = re.search(r"weibo\.com/\d+/([A-Za-z0-9]+)", url)
            if not m:
                print("    [SKIP] Cannot parse post ID")
                continue
            short_id = m.group(1)

            # Navigate to post page — this passes bot detection and sets session
            detail_url = f"https://m.weibo.cn/detail/{short_id}"
            try:
                await page.goto(detail_url, wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(2)
            except Exception as e:
                print(f"    [WARN] Page load failed: {e}")

            # Resolve numeric post ID via API (needed for stable pagination)
            resolve_js = f"""
            async () => {{
                const r = await fetch(
                    'https://m.weibo.cn/statuses/show?id={short_id}',
                    {{credentials: 'include'}}
                );
                const d = await r.json();
                return String(d?.data?.id || d?.data?.idstr || '{short_id}');
            }}
            """
            try:
                post_id = await page.evaluate(resolve_js)
            except Exception:
                post_id = short_id
            print(f"    post_id = {post_id}")

            # Fetch comments
            print(f"    Fetching up to {args.max:,} comments …")
            try:
                comments = await fetch_comments_browser(page, post_id, args.max, args.delay)
            except Exception as e:
                print(f"    [ERROR] {e}")
                comments = []

            entry = {
                "post_url":           url,
                "post_id":            post_id,
                "incident":           target["incident"],
                "declared_comments":  target["declared_comments"],
                "scraped_at":         datetime.now().isoformat(),
                "comments_collected": len(comments),
                "comments":           comments,
            }
            results.append(entry)
            print(f"    ✓ {len(comments)} comments collected")

            save(results, out_path)
            await asyncio.sleep(args.delay)

        await browser.close()

    print(f"\n{'='*50}")
    total_comments = sum(r["comments_collected"] for r in results)
    print(f"Done. {len(results)} posts → {total_comments:,} comments → {out_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max",      type=int,   default=1000)
    parser.add_argument("--min-post", type=int,   default=1000, dest="min_post")
    parser.add_argument("--out",      default="deep_comments.json")
    parser.add_argument("--delay",    type=float, default=2.0)
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
