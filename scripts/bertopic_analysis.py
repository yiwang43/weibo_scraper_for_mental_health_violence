"""
bertopic_analysis.py
====================
Runs BERTopic on the scraped Weibo comments to surface latent discourse themes.
Uses a multilingual sentence transformer that handles Chinese text well.

USAGE:
  python scripts/bertopic_analysis.py
  python scripts/bertopic_analysis.py --min-chars 8 --topics 15

OUTPUT (in data/processed/):
  topic_summary.csv      — one row per topic: label, size, top keywords
  comments_with_topics.csv — enriched_comments.csv + topic_id + topic_label
  topic_examples.txt     — top 5 representative comments per topic (for close reading)

REQUIRES:
  pip install bertopic sentence-transformers
"""

import argparse
import csv
import re
from pathlib import Path

import pandas as pd
from bertopic import BERTopic
from sentence_transformers import SentenceTransformer

BASE = Path(__file__).parent.parent


def clean_text(text: str) -> str:
    text = re.sub(r"http\S+", "", text)           # remove URLs
    text = re.sub(r"@\S+", "", text)               # remove @mentions
    text = re.sub(r"#[^#]+#", "", text)            # remove hashtags
    text = re.sub(r"\s+", " ", text).strip()
    return text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-chars", type=int, default=8,
                        help="Drop comments shorter than this (default: 8)")
    parser.add_argument("--topics",    type=int, default=None,
                        help="Force N topics; omit to let BERTopic decide")
    parser.add_argument("--model",     default="paraphrase-multilingual-MiniLM-L12-v2",
                        help="Sentence transformer model name")
    args = parser.parse_args()

    # ── Load data ─────────────────────────────────────────────────────────
    print("Loading comments …")
    df = pd.read_csv(BASE / "data/processed/enriched_comments.csv", encoding="utf-8-sig")
    print(f"  Total rows: {len(df)}")

    df["clean_text"] = df["text"].fillna("").apply(clean_text)
    df = df[df["clean_text"].str.len() >= args.min_chars].copy()
    print(f"  After filtering short/empty: {len(df)} comments")

    docs = df["clean_text"].tolist()

    # ── Embed ─────────────────────────────────────────────────────────────
    print(f"\nEmbedding with {args.model} …")
    model = SentenceTransformer(args.model)
    embeddings = model.encode(docs, show_progress_bar=True, batch_size=64)

    # ── Fit BERTopic ──────────────────────────────────────────────────────
    print("\nFitting BERTopic …")
    topic_model = BERTopic(
        embedding_model=model,
        nr_topics=args.topics,     # None = auto
        min_topic_size=10,
        verbose=True,
        language="multilingual",
    )
    topics, probs = topic_model.fit_transform(docs, embeddings)
    df["topic_id"] = topics

    topic_info = topic_model.get_topic_info()
    print(f"\nFound {len(topic_info) - 1} topics "
          f"(plus {sum(1 for t in topics if t == -1)} outlier comments)")

    # ── Save topic summary ────────────────────────────────────────────────
    out_dir = BASE / "data/processed"

    rows = []
    for _, row in topic_info.iterrows():
        tid = row["Topic"]
        if tid == -1:
            label = "outliers / noise"
        else:
            top_words = topic_model.get_topic(tid)
            label = "  |  ".join(w for w, _ in top_words[:6])
        rows.append({
            "topic_id":    tid,
            "size":        row["Count"],
            "top_keywords": label,
        })

    topic_summary = pd.DataFrame(rows)
    topic_summary.to_csv(out_dir / "topic_summary.csv", index=False, encoding="utf-8-sig")
    print(f"\nTopic summary → data/processed/topic_summary.csv")
    print(topic_summary.to_string(index=False))

    # ── Merge topic labels back into comments ─────────────────────────────
    keyword_map = {r["topic_id"]: r["top_keywords"] for r in rows}
    df["topic_label"] = df["topic_id"].map(keyword_map)

    out_cols = [
        "incident", "incident_date", "post_url",
        "source", "account_type",
        "comment_id", "user_screen_name", "text", "likes",
        "created_at", "is_reply",
        "topic_id", "topic_label",
    ]
    out_cols = [c for c in out_cols if c in df.columns]
    df[out_cols].to_csv(out_dir / "comments_with_topics.csv",
                        index=False, encoding="utf-8-sig")
    print(f"Comments with topics → data/processed/comments_with_topics.csv")

    # ── Write example comments per topic (for close reading) ─────────────
    with open(out_dir / "topic_examples.txt", "w", encoding="utf-8") as f:
        for tid in sorted(topic_info["Topic"].tolist()):
            if tid == -1:
                continue
            kw = keyword_map.get(tid, "")
            f.write(f"\n{'='*60}\n")
            f.write(f"TOPIC {tid}: {kw}\n")
            f.write(f"{'='*60}\n")
            subset = df[df["topic_id"] == tid].sort_values("likes", ascending=False)
            for _, row in subset.head(5).iterrows():
                f.write(f"\n[{row['likes']} likes | {row.get('incident','')}]\n")
                f.write(f"{row['text']}\n")
    print(f"Topic examples → data/processed/topic_examples.txt")


if __name__ == "__main__":
    main()
