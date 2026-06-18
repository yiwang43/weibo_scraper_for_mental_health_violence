"""
visualize_topics.py
===================
Generates three charts from the BERTopic results:

  1. topic_sizes.png       — horizontal bar chart, topics sized by comment count
  2. topic_heatmap.png     — heatmap of topic distribution across incidents
  3. topic_likes.png       — avg likes per topic (engagement proxy)

OUTPUT: data/processed/figures/
"""

import warnings
warnings.filterwarnings("ignore")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import pandas as pd
import numpy as np
from pathlib import Path

BASE    = Path(__file__).parent.parent
OUT_DIR = BASE / "data/processed/figures"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Font: use system CJK font so Chinese characters render ────────────────
plt.rcParams["font.family"] = ["Arial Unicode MS", "PingFang SC",
                                "Heiti TC", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# ── Load data ─────────────────────────────────────────────────────────────
df = pd.read_csv(BASE / "data/processed/comments_with_topics.csv", encoding="utf-8-sig")
df = df[df["topic_id"] >= 0].copy()   # drop outliers

# ── Theme colour mapping ──────────────────────────────────────────────────
THEME_COLORS = {
    "Mental Illness & Law":     "#d62728",
    "Punishment & Justice":     "#ff7f0e",
    "Child Victims":            "#2ca02c",
    "Public Safety & Fear":     "#1f77b4",
    "Media & Info Control":     "#9467bd",
    "Incident-Specific":        "#8c564b",
}

TOPIC_THEMES = {
    0:  "Mental Illness & Law",
    20: "Mental Illness & Law",
    8:  "Punishment & Justice",
    9:  "Punishment & Justice",
    11: "Punishment & Justice",
    12: "Punishment & Justice",
    13: "Punishment & Justice",
    19: "Punishment & Justice",
    1:  "Child Victims",
    3:  "Child Victims",
    18: "Child Victims",
    21: "Child Victims",
    23: "Child Victims",
    4:  "Public Safety & Fear",
    5:  "Public Safety & Fear",
    10: "Public Safety & Fear",
    7:  "Media & Info Control",
    17: "Media & Info Control",
    6:  "Incident-Specific",
    2:  "Incident-Specific",
    14: "Incident-Specific",
    15: "Incident-Specific",
    16: "Incident-Specific",
    22: "Incident-Specific",
    24: "Incident-Specific",
}

SHORT_LABELS = {
    0:  "Mental illness as legal shield",
    1:  "School/child safety measures",
    2:  "Mixed reactions",
    3:  "Outrage: attacking children",
    4:  "General fear / 'anyone could be a victim'",
    5:  "Security infra debate",
    6:  "Comparative safety / patriotic discourse",
    7:  "Suppressed news / opaque reporting",
    8:  "Death penalty arguments",
    9:  "Retributive anger",
    10: "Premeditation / weapon carrying",
    11: "Legal system will prevail",
    12: "Support for court verdicts",
    13: "Execute immediately",
    14: "Vehicle ramming sentencing (景德镇)",
    15: "Hospital security (瑞金医院)",
    16: "Grief for victims",
    17: "Media critique",
    18: "Shattered families",
    19: "Praise for law enforcement",
    20: "Recidivism / fear of release",
    21: "Prayers for victims' recovery",
    22: "Nationalist framing (Shenzhen)",
    23: "Direct punishment calls",
    24: "Perpetrator-specific outrage",
}

topic_stats = (
    df.groupby("topic_id")
      .agg(count=("text", "size"), avg_likes=("likes", "mean"))
      .reset_index()
      .sort_values("count", ascending=False)
)
topic_stats["label"]  = topic_stats["topic_id"].map(SHORT_LABELS)
topic_stats["theme"]  = topic_stats["topic_id"].map(TOPIC_THEMES)
topic_stats["color"]  = topic_stats["theme"].map(THEME_COLORS)


# ═══════════════════════════════════════════════════════════════════════════
# Chart 1 — Topic sizes (horizontal bar)
# ═══════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(12, 10))

bars = ax.barh(
    topic_stats["label"],
    topic_stats["count"],
    color=topic_stats["color"],
    edgecolor="white", linewidth=0.5,
    height=0.7,
)

# Annotate count
for bar, val in zip(bars, topic_stats["count"]):
    ax.text(bar.get_width() + 1.5, bar.get_y() + bar.get_height() / 2,
            str(val), va="center", fontsize=9, color="#333333")

ax.set_xlabel("Number of comments", fontsize=12)
ax.set_title("BERTopic Results: Discourse Themes in Weibo Comments\non Stranger Violence (2010–2025)",
             fontsize=14, fontweight="bold", pad=15)
ax.set_xlim(0, topic_stats["count"].max() * 1.12)
ax.invert_yaxis()
ax.spines[["top", "right"]].set_visible(False)
ax.tick_params(axis="y", labelsize=9.5)

legend_patches = [mpatches.Patch(color=c, label=t) for t, c in THEME_COLORS.items()]
ax.legend(handles=legend_patches, loc="lower right", fontsize=9,
          title="Theme", title_fontsize=9, framealpha=0.8)

plt.tight_layout()
plt.savefig(OUT_DIR / "topic_sizes.png", dpi=150, bbox_inches="tight")
plt.close()
print("Saved: topic_sizes.png")


# ═══════════════════════════════════════════════════════════════════════════
# Chart 2 — Heatmap: topics × top incidents
# ═══════════════════════════════════════════════════════════════════════════
# Keep only the top 15 incidents by comment count and top 12 topics
top_incidents = (df.groupby("incident")["text"].count()
                   .nlargest(15).index.tolist())
top_topics    = topic_stats.nlargest(12, "count")["topic_id"].tolist()

heat_df = df[df["incident"].isin(top_incidents) & df["topic_id"].isin(top_topics)]
pivot   = (heat_df.groupby(["incident", "topic_id"])
                  .size()
                  .unstack(fill_value=0)
                  .reindex(top_incidents))

# Normalise rows (% of each incident's comments)
pivot_pct = pivot.div(pivot.sum(axis=1), axis=0) * 100
pivot_pct.columns = [SHORT_LABELS.get(c, c) for c in pivot_pct.columns]

# Shorten incident names
pivot_pct.index = [i[:18] + "…" if len(i) > 18 else i for i in pivot_pct.index]

fig, ax = plt.subplots(figsize=(14, 8))
import seaborn as sns
sns.heatmap(
    pivot_pct,
    ax=ax,
    cmap="YlOrRd",
    annot=True, fmt=".0f",
    annot_kws={"size": 8},
    linewidths=0.4,
    linecolor="#dddddd",
    cbar_kws={"label": "% of incident's comments"},
)
ax.set_title("Topic Distribution Across Top 15 Incidents\n(% of each incident's comments)",
             fontsize=13, fontweight="bold", pad=12)
ax.set_xlabel("")
ax.set_ylabel("")
ax.tick_params(axis="x", labelsize=8.5, rotation=35)
ax.tick_params(axis="y", labelsize=9)
plt.tight_layout()
plt.savefig(OUT_DIR / "topic_heatmap.png", dpi=150, bbox_inches="tight")
plt.close()
print("Saved: topic_heatmap.png")


# ═══════════════════════════════════════════════════════════════════════════
# Chart 3 — Avg likes per topic (engagement proxy)
# ═══════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(12, 8))

top12 = topic_stats.nlargest(12, "count").sort_values("avg_likes", ascending=True)

bars = ax.barh(
    top12["label"],
    top12["avg_likes"],
    color=top12["color"],
    edgecolor="white", linewidth=0.5,
    height=0.65,
)
for bar, val in zip(bars, top12["avg_likes"]):
    ax.text(bar.get_width() + 20, bar.get_y() + bar.get_height() / 2,
            f"{val:,.0f}", va="center", fontsize=9)

ax.set_xlabel("Average likes per comment", fontsize=12)
ax.set_title("Average Engagement (Likes) per Topic\n(top 12 topics by size)",
             fontsize=14, fontweight="bold", pad=15)
ax.set_xlim(0, top12["avg_likes"].max() * 1.15)
ax.spines[["top", "right"]].set_visible(False)
ax.tick_params(axis="y", labelsize=9.5)

legend_patches = [mpatches.Patch(color=c, label=t) for t, c in THEME_COLORS.items()
                  if t in top12["theme"].values]
ax.legend(handles=legend_patches, loc="lower right", fontsize=9,
          title="Theme", title_fontsize=9, framealpha=0.8)

plt.tight_layout()
plt.savefig(OUT_DIR / "topic_likes.png", dpi=150, bbox_inches="tight")
plt.close()
print("Saved: topic_likes.png")

print(f"\nAll figures saved to: {OUT_DIR}")
