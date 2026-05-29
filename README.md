# Weibo Scraper — Mental Health & Violence Project

Research data collection for studying public discourse around stranger violence incidents on Weibo.

---

## Folder Structure

```
├── data/
│   ├── raw/
│   │   ├── Research Data - Sheet1.csv   # hand-coded incident spreadsheet
│   │   ├── comments.json                # scraped comments (main URLs)
│   │   └── new_comments.json            # scraped comments (additional URLs)
│   └── processed/
│       ├── enriched_comments.csv        # ★ main analysis file
│       ├── enriched_posts.csv           # post-level summary
│       └── comments.csv                 # flat comments without metadata
├── scripts/
│   ├── weibo_scraper.py                 # main scraper
│   ├── build_enriched.py                # joins raw data → enriched CSVs
│   ├── json_to_csv.py                   # converts comments.json to CSV
│   └── playwright_deep_scraper.py       # browser-based scraper (experimental)
├── urls.txt                             # Weibo post URLs grouped by incident
├── cookies.json                         # session credentials — do not share
└── README.md
```

---

## Key Files

### For analysis

| File | Description |
|------|-------------|
| `data/processed/enriched_comments.csv` | **Main analysis file.** 2,220 rows, one per comment. Includes incident name, date, source, post summary, and all comment fields. |
| `data/processed/enriched_posts.csv` | One row per Weibo post (87 posts). Good for post-level analysis. |
| `data/raw/Research Data - Sheet1.csv` | Original hand-coded spreadsheet with incident metadata, engagement counts, and manually curated comments. |

### Scripts

| File | Description |
|------|-------------|
| `scripts/weibo_scraper.py` | Main scraper. Reads `urls.txt`, pulls comments, saves to JSON. |
| `scripts/build_enriched.py` | Joins raw JSON + spreadsheet → enriched CSVs. Re-run whenever source data changes. |

---

## How to re-run

```bash
# 1. Scrape comments
python scripts/weibo_scraper.py --urls urls.txt --out data/raw/comments.json --max 300

# 2. Rebuild enriched CSVs
cd scripts && python build_enriched.py
```

---

## Dataset notes

- **2,220 comments** across **87 posts** covering **25 incidents** (2010–2025)
- Comments are the top-ranked publicly visible comments per post. Weibo moderates heavily on sensitive topics, so the accessible pool per post is typically 20–40 comments regardless of declared comment counts.
- Each comment is linked to its incident via URL matching with the spreadsheet.
- The `account_type` column distinguishes news media accounts from other users.
