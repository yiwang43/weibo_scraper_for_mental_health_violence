# Weibo Scraper — Mental Health & Violence Project

Research data collection for studying public discourse around stranger violence incidents on Weibo.

---

## Folder Structure

```
├── data/
│   ├── raw/
│   │   ├── Research Data - Sheet1.csv   # hand-coded incident spreadsheet
│   │   ├── comments.json                # scraped comments (main URLs)
│   │   ├── new_comments.json            # scraped comments (additional URLs)
│   │   └── incident_coding.csv        
│   └── processed/
│       ├── enriched_comments.csv        # - main analysis file (2,220 comments)
│       ├── enriched_posts.csv           # post-level summary (87 posts)
│       ├── comments.csv                 # flat comments without metadata
│       ├── comments_with_topics.csv     # enriched_comments + BERTopic labels
│       ├── topic_summary.csv            # 25 topics with sizes and keywords
│       ├── topic_examples.txt           # top 5 comments per topic (for close reading)
│       ├── BERTopic_Report.md           # analysis report
│       └── figures/
│           ├── topic_sizes.png          # bar chart: topic sizes by comment count
│           ├── topic_heatmap.png        # heatmap: topics × top 15 incidents
│           └── topic_likes.png          # bar chart: avg likes per topic
├── scripts/
│   ├── weibo_scraper.py                 # main scraper
│   ├── build_enriched.py                # joins raw data → enriched CSVs
│   ├── bertopic_analysis.py             # runs BERTopic topic modeling
│   ├── visualize_topics.py              # generates the three figures
│   ├── json_to_csv.py                   # converts comments.json to CSV
│   ├── search_scraper.py                # searches Weibo hashtags for new posts
│   └── playwright_deep_scraper.py       # browser-based scraper (experimental)
├── urls.txt                             # Weibo post URLs grouped by incident
├── cookies.json                         # session credentials 
└── README.md
```

---

## Key Files

### For analysis

| File | Description |
|------|-------------|
| `data/processed/enriched_comments.csv` | **Main analysis file.** 2,220 rows, one per comment. Includes incident name, date, source, post summary, and all comment fields. |
| `data/processed/enriched_posts.csv` | One row per Weibo post (87 posts). Good for post-level analysis. |
| `data/processed/comments_with_topics.csv` | enriched_comments + BERTopic topic ID and label per comment. |
| `data/processed/BERTopic_Report.md` | **Professor-facing report.** 25 topics grouped into 6 themes, translated examples, key findings, and figures. |
| `data/raw/Research Data - Sheet1.csv` | Original hand-coded spreadsheet with incident metadata, engagement counts, and manually curated comments. |
| `data/raw/incident_coding.csv` | Template for coding whether each incident involved mental illness (confirmed / alleged / none / unclear). Fill this in to enable cross-incident comparison. |

### Scripts

| File | Description |
|------|-------------|
| `scripts/weibo_scraper.py` | Main scraper. Reads `urls.txt`, pulls comments, saves to JSON. |
| `scripts/build_enriched.py` | Joins raw JSON + spreadsheet → enriched CSVs. Re-run whenever source data changes. |
| `scripts/bertopic_analysis.py` | Runs BERTopic on `enriched_comments.csv`. Outputs topic CSVs and examples. |
| `scripts/visualize_topics.py` | Generates three figures from BERTopic results. Outputs to `data/processed/figures/`. |
| `scripts/search_scraper.py` | Searches Weibo hashtags for new posts not already in the dataset. |

---

## How to re-run

```bash
# 1. Scrape comments
python scripts/weibo_scraper.py --urls urls.txt --out data/raw/comments.json --max 300

# 2. Rebuild enriched CSVs
python scripts/build_enriched.py

# 3. Run BERTopic topic modeling (requires sklearn-env)
/opt/anaconda3/envs/sklearn-env/bin/python scripts/bertopic_analysis.py

# 4. Generate figures
/opt/anaconda3/envs/sklearn-env/bin/python scripts/visualize_topics.py
```

---

## Dataset notes

- **2,220 comments** across **87 posts** covering **35 incidents** (2010–2025)
- Comments are the top-ranked publicly visible comments per post. Weibo moderates heavily on sensitive topics, so the accessible pool per post is typically 20–40 comments regardless of declared comment counts.
- Each comment is linked to its incident via URL matching with the spreadsheet.
- The `account_type` column distinguishes news media accounts from other users.
- BERTopic was run on 1,265 comments (after filtering < 8 characters), producing 25 topics and 345 outliers.
