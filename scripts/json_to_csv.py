"""
json_to_csv.py
==============
Flattens weibo_comments.json into a CSV where each row is one comment,
with the incident/post metadata columns repeated.

USAGE:
  python json_to_csv.py --in weibo_comments.json --out weibo_comments.csv

Columns in output:
  post_url, post_id, scraped_at, post_text,
  comment_id, user_screen_name, text, likes,
  created_at, is_reply, reply_to_screen_name
"""

import argparse
import json
import csv
import sys
from pathlib import Path


def flatten(in_path: str, out_path: str) -> None:
    data = json.loads(Path(in_path).read_text(encoding="utf-8"))

    rows = []
    for post in data:
        meta = {
            "post_url":   post.get("post_url", ""),
            "post_id":    post.get("post_id", ""),
            "scraped_at": post.get("scraped_at", ""),
            "post_text":  post.get("post_text", ""),
            "error":      post.get("error", ""),
        }
        comments = post.get("comments", [])
        if not comments:
            rows.append({**meta})
            continue
        for c in comments:
            rows.append({
                **meta,
                "comment_id":           c.get("comment_id", ""),
                "user_screen_name":     c.get("user_screen_name", ""),
                "text":                 c.get("text", ""),
                "likes":                c.get("likes", 0),
                "created_at":           c.get("created_at", ""),
                "is_reply":             c.get("is_reply", False),
                "reply_to_screen_name": c.get("reply_to_screen_name", ""),
            })

    if not rows:
        print("[WARN] No data found.")
        sys.exit(0)

    fieldnames = [
        "post_url", "post_id", "scraped_at", "post_text",
        "comment_id", "user_screen_name", "text", "likes",
        "created_at", "is_reply", "reply_to_screen_name", "error",
    ]

    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"Written {len(rows)} rows → {out_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--in",  dest="inp", default="weibo_comments.json")
    parser.add_argument("--out", dest="out", default="weibo_comments.csv")
    args = parser.parse_args()
    flatten(args.inp, args.out)


if __name__ == "__main__":
    main()
