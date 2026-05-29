"""
build_enriched.py
=================
Merges scraped comments with spreadsheet metadata to produce
an analysis-ready enriched CSV. Each row = one comment, with
incident-level and post-level metadata attached.

Also outputs a second CSV where each row = one post (for post-level analysis).

USAGE:
  python build_enriched.py
"""

import csv
import json
import re
from pathlib import Path


def normalize_url(url: str) -> str:
    url = url.strip()
    url = url.split("#")[0]
    url = url.split("?")[0]
    return url.rstrip("/")


def load_comments(json_path: str) -> list[dict]:
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    rows = []
    for post in data:
        meta = {
            "post_url":           normalize_url(post.get("post_url", "")),
            "post_id":            post.get("post_id", ""),
            "scraped_at":         post.get("scraped_at", ""),
            "post_text_api":      post.get("post_text", ""),
            "comments_collected": post.get("comments_collected", 0),
        }
        for c in post.get("comments", []):
            rows.append({**meta, **c})
    return rows


def load_spreadsheet(csv_path: str) -> list[dict]:
    with open(csv_path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    # Forward-fill incident name and date (only on first row of each incident)
    last_incident = ""
    last_date = ""
    for r in rows:
        if r.get("事件 incident", "").strip():
            last_incident = r["事件 incident"].strip()
            last_date = r.get("日期Date", "").strip()
        r["incident"] = last_incident
        r["incident_date"] = last_date

    return rows


def main():
    base = Path(__file__).parent.parent  # repo root

    # ── Load all scraped comments ─────────────────────────────────────────
    comments = load_comments(base / "data/raw/comments.json")
    new_comments = load_comments(base / "data/raw/new_comments.json")
    all_comments = comments + new_comments
    print(f"Total scraped comments: {len(all_comments)}")

    # ── Load spreadsheet ──────────────────────────────────────────────────
    sheet_rows = load_spreadsheet(base / "data/raw/Research Data - Sheet1.csv")

    # Build URL → sheet row lookup (one sheet row per URL)
    sheet_by_url: dict[str, dict] = {}
    for r in sheet_rows:
        url = normalize_url(r.get("URL", ""))
        if url:
            sheet_by_url[url] = r

    # ── Join ──────────────────────────────────────────────────────────────
    enriched = []
    unmatched_posts = set()

    for c in all_comments:
        url = c["post_url"]
        sheet = sheet_by_url.get(url, {})

        if not sheet:
            unmatched_posts.add(url)

        row = {
            # ── Incident metadata ────────────────────────────────────────
            "incident":           sheet.get("incident", ""),
            "incident_date":      sheet.get("incident_date", ""),
            "post_title":         sheet.get("标题", ""),
            "source":             sheet.get("来源", ""),
            "account_type":       sheet.get("用户属性", "").strip(),
            "tags":               sheet.get("Tag ", "").strip(),
            "engagement":         sheet.get("转赞评 ", "").strip(),
            "post_summary":       sheet.get("微博内容摘要", "").strip(),
            # ── Post metadata ────────────────────────────────────────────
            "post_url":           c["post_url"],
            "post_id":            c["post_id"],
            "scraped_at":         c["scraped_at"],
            # ── Comment fields ───────────────────────────────────────────
            "comment_id":         c.get("comment_id", ""),
            "user_screen_name":   c.get("user_screen_name", ""),
            "text":               c.get("text", ""),
            "likes":              c.get("likes", 0),
            "created_at":         c.get("created_at", ""),
            "is_reply":           c.get("is_reply", False),
            "reply_to_screen_name": c.get("reply_to_screen_name", ""),
        }
        enriched.append(row)

    print(f"Matched: {len(enriched) - len([r for r in enriched if not r['incident']])} comments have incident name")
    print(f"Unmatched post URLs: {len(unmatched_posts)}")
    if unmatched_posts:
        for u in sorted(unmatched_posts)[:5]:
            print(f"  {u}")

    # ── Write enriched comment-level CSV ─────────────────────────────────
    fieldnames = [
        "incident", "incident_date",
        "post_title", "source", "account_type", "tags", "engagement",
        "post_url", "post_id", "scraped_at",
        "post_summary",
        "comment_id", "user_screen_name", "text", "likes",
        "created_at", "is_reply", "reply_to_screen_name",
    ]

    out_dir = base / "data/processed"
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(out_dir / "enriched_comments.csv", "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(enriched)
    print(f"\nWritten: data/processed/enriched_comments.csv ({len(enriched)} rows)")

    # ── Write post-level CSV (one row per post, for post-level analysis) ──
    seen_posts = set()
    post_rows = []
    for r in enriched:
        url = r["post_url"]
        if url in seen_posts:
            continue
        seen_posts.add(url)
        post_rows.append({
            "incident":       r["incident"],
            "incident_date":  r["incident_date"],
            "post_title":     r["post_title"],
            "source":         r["source"],
            "account_type":   r["account_type"],
            "tags":           r["tags"],
            "engagement":     r["engagement"],
            "post_url":       r["post_url"],
            "post_summary":   r["post_summary"],
            "comments_in_dataset": sum(
                1 for x in enriched if x["post_url"] == url
            ),
        })

    post_fieldnames = [
        "incident", "incident_date", "post_title", "source", "account_type",
        "tags", "engagement", "post_url", "post_summary", "comments_in_dataset",
    ]
    with open(out_dir / "enriched_posts.csv", "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=post_fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(post_rows)
    print(f"Written: data/processed/enriched_posts.csv ({len(post_rows)} rows)")

    # ── Summary ───────────────────────────────────────────────────────────
    incidents = {}
    for r in enriched:
        inc = r["incident"] or "(unknown)"
        incidents[inc] = incidents.get(inc, 0) + 1

    print(f"\nComments per incident:")
    for inc, n in sorted(incidents.items(), key=lambda x: -x[1]):
        print(f"  {n:4d}  {inc}")


if __name__ == "__main__":
    main()
