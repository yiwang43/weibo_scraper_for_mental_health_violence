# Weibo Scraper — Mental Health & Violence Project

Research data collection for studying public discourse around stranger violence incidents on Weibo.

---

## Key Files

### Data (use these for analysis)

| File | Description |
|------|-------------|
| `enriched_comments.csv` | **Main analysis file.** 2,220 rows, one per scraped comment. Includes incident name, date, post source, post summary, and all comment fields. |
| `enriched_posts.csv` | One row per Weibo post (87 posts). 

| `Research Data.csv` | Original hand-coded spreadsheet with incident metadata, post titles, sources, engagement counts, and manually curated comments. |

### Scripts

| File | Description |
|------|-------------|
| `weibo_scraper.py` | Main scraper. Reads URLs from `urls.txt`, pulls comments via two-phase approach (hotflow + chronological), saves to JSON. |
| `build_enriched.py` | Joins `comments.json` + `new_comments.json` with spreadsheet metadata to produce the enriched CSVs. Re-run this if either source is updated. |
| `json_to_csv.py` | Converts raw `comments.json` to flat CSV. Used before `build_enriched.py` existed. |

### Input

| File | Description |
|------|-------------|
| `urls.txt` | All Weibo post URLs to scrape, grouped by incident. |
| `cookies.json` | Browser cookies exported from weibo.com (required for authentication). **contains session credentials.** |


---

## Dataset notes

- **2,220 comments** across **87 posts** covering **25 incidents** (2010–2025)
- Comments are the top-ranked publicly visible comments per post. Weibo moderates heavily on sensitive topics, so the accessible pool per post is typically 20–40 comments regardless of declared comment counts.
- Each comment is linked to its incident via URL matching with the spreadsheet.
- The `account_type` column distinguishes news media accounts from other users.
