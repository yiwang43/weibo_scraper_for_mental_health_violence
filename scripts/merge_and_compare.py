"""
merge_and_compare.py
====================
1. Merges mental illness coding into comments_with_topics.csv
2. Validates BERTopic labels against manual annotation
3. Produces cross-group topic comparison (confirmed vs alleged vs none vs unclear)

OUTPUT: data/processed/
  - comments_final.csv          — full dataset with mental_illness column
  - topic_by_mi_group.csv       — topic % per mental illness group
  - annotation_accuracy.csv     — BERTopic accuracy vs manual labels
  - figures/mi_comparison.png   — bar chart comparing topic distributions
  - figures/annotation_check.png — BERTopic accuracy chart
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
OUT_DIR = BASE / "data/processed"
FIG_DIR = OUT_DIR / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

plt.rcParams["font.family"] = ["Arial Unicode MS", "PingFang SC", "Heiti TC", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# ── Load data ─────────────────────────────────────────────────────────────────

df      = pd.read_csv(OUT_DIR / "comments_with_topics.csv", encoding="utf-8-sig")
coding  = pd.read_csv(BASE / "data/raw/incident_coding.csv", encoding="utf-8-sig")
annot   = pd.read_csv(BASE / "data/raw/comment_annotation_sample.csv", encoding="utf-8-sig", index_col=0)

print(f"Comments loaded:       {len(df)}")
print(f"Incidents coded:       {len(coding)}  ({coding['mental_illness'].notna().sum()} with MI label)")
print(f"Annotated comments:    {len(annot)}\n")

# ── 1. Merge mental illness coding ────────────────────────────────────────────

df = df.merge(
    coding[["incident", "mental_illness"]],
    on="incident", how="left"
)

# Forward-fill missing incident names (blank rows in raw data)
df["mental_illness"] = df["mental_illness"].fillna("unknown")

comments_final = OUT_DIR / "comments_final.csv"
df.to_csv(comments_final, index=False, encoding="utf-8-sig")
print(f"Saved: comments_final.csv")
print(df["mental_illness"].value_counts().to_string())
print()

# ── 2. BERTopic accuracy vs manual annotation ─────────────────────────────────

# bert_correct column: yes / no / partial
valid = annot[annot["bert_correct"].notna() & (annot["bert_correct"] != "")].copy()
valid["bert_correct"] = valid["bert_correct"].str.strip().str.lower()

accuracy = valid["bert_correct"].value_counts()
total    = len(valid)
pct      = (accuracy / total * 100).round(1)

acc_df = pd.DataFrame({"count": accuracy, "pct": pct}).reset_index()
acc_df.columns = ["verdict", "count", "pct"]
acc_df.to_csv(OUT_DIR / "annotation_accuracy.csv", index=False, encoding="utf-8-sig")

print("BERTopic accuracy vs manual annotation:")
for _, row in acc_df.iterrows():
    print(f"  {row['verdict']:10s}  {row['count']:3d}  ({row['pct']}%)")
print()

# By theme
print("Accuracy breakdown by BERTopic theme:")
by_theme = valid.groupby("theme")["bert_correct"].value_counts(normalize=True).mul(100).round(1)
print(by_theme.to_string())
print()

# mental_illness_mentioned accuracy (bert vs manual)
mi_annot = annot[annot["mental_illness_mentioned"].notna()].copy()
mi_annot["mental_illness_mentioned"] = mi_annot["mental_illness_mentioned"].str.strip().str.lower()
mi_yes = (mi_annot["mental_illness_mentioned"] == "yes").sum()
mi_no  = (mi_annot["mental_illness_mentioned"] == "no").sum()
print(f"Manual annotation: {mi_yes} comments mention mental illness, {mi_no} do not")
bert_mi_topic = (mi_annot["theme"] == "Mental Illness & Law").sum()
manual_mi     = (mi_annot["mental_illness_mentioned"] == "yes").sum()
print(f"BERTopic MI theme count: {bert_mi_topic}  |  Manual MI-mentioned count: {manual_mi}")
print()

# sentiment distribution among MI-mentioned comments
mi_comments = mi_annot[mi_annot["mental_illness_mentioned"] == "yes"]
print("Sentiment toward MI defense (manual annotation):")
print(mi_comments["sentiment_toward_mi_defense"].value_counts().to_string())
print()

# ── 3. Cross-group topic comparison ───────────────────────────────────────────

THEME_MAP = {
    0:  "Mental Illness & Law",   20: "Mental Illness & Law",
    8:  "Punishment & Justice",   9:  "Punishment & Justice",
    11: "Punishment & Justice",   12: "Punishment & Justice",
    13: "Punishment & Justice",   19: "Punishment & Justice",
    1:  "Child Victims",          3:  "Child Victims",
    18: "Child Victims",          21: "Child Victims",   23: "Child Victims",
    4:  "Public Safety & Fear",   5:  "Public Safety & Fear",  10: "Public Safety & Fear",
    7:  "Media & Info Control",   17: "Media & Info Control",
    6:  "Incident-Specific",      2:  "Incident-Specific",
    14: "Incident-Specific",      15: "Incident-Specific",
    16: "Incident-Specific",      22: "Incident-Specific",  24: "Incident-Specific",
}

THEME_COLORS = {
    "Mental Illness & Law":  "#d62728",
    "Punishment & Justice":  "#ff7f0e",
    "Child Victims":         "#2ca02c",
    "Public Safety & Fear":  "#1f77b4",
    "Media & Info Control":  "#9467bd",
    "Incident-Specific":     "#8c564b",
}

df_topics = df[df["topic_id"] >= 0].copy()
df_topics["theme"] = df_topics["topic_id"].map(THEME_MAP)

MI_ORDER = ["confirmed", "alleged", "unclear", "none"]
present  = [g for g in MI_ORDER if g in df_topics["mental_illness"].values]

pivot = (
    df_topics.groupby(["mental_illness", "theme"])
             .size()
             .unstack(fill_value=0)
             .reindex(present)
)
pivot_pct = pivot.div(pivot.sum(axis=1), axis=0) * 100

pivot_pct.to_csv(OUT_DIR / "topic_by_mi_group.csv", encoding="utf-8-sig")
print("Topic % by mental illness group:")
print(pivot_pct.round(1).to_string())
print()

# ── Figure: MI comparison stacked bar ────────────────────────────────────────

fig, ax = plt.subplots(figsize=(11, 6))
themes  = [t for t in THEME_COLORS if t in pivot_pct.columns]
colors  = [THEME_COLORS[t] for t in themes]

bottom = np.zeros(len(present))
for theme, color in zip(themes, colors):
    vals = pivot_pct[theme].values if theme in pivot_pct.columns else np.zeros(len(present))
    bars = ax.bar(present, vals, bottom=bottom, color=color, label=theme,
                  edgecolor="white", linewidth=0.6)
    for bar, val in zip(bars, vals):
        if val >= 6:
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_y() + bar.get_height() / 2,
                    f"{val:.0f}%", ha="center", va="center",
                    fontsize=8.5, color="white", fontweight="bold")
    bottom += vals

# annotate n per group
for i, g in enumerate(present):
    n = int(pivot.loc[g].sum())
    ax.text(i, 101, f"n={n}", ha="center", va="bottom", fontsize=9, color="#444")

ax.set_ylim(0, 113)
ax.set_xlabel("Mental Illness Framing of Incident", fontsize=12)
ax.set_ylabel("% of comments (within group)", fontsize=12)
ax.set_title("Topic Distribution by Mental Illness Status of Incident\n(BERTopic themes, outliers excluded)",
             fontsize=13, fontweight="bold", pad=12)
ax.spines[["top", "right"]].set_visible(False)

legend_patches = [mpatches.Patch(color=THEME_COLORS[t], label=t) for t in themes]
ax.legend(handles=legend_patches, loc="upper center", bbox_to_anchor=(0.5, -0.1),
          fontsize=9, title="Theme", title_fontsize=9, framealpha=0.85, ncol=3)

plt.tight_layout()
plt.savefig(FIG_DIR / "mi_comparison.png", dpi=150, bbox_inches="tight")
plt.close()
print("Saved: figures/mi_comparison.png")

# ── Figure: BERTopic accuracy pie ─────────────────────────────────────────────

fig, ax = plt.subplots(figsize=(7, 5))
colors_pie = ["#2ca02c", "#d62728", "#ff7f0e"]
wedges, texts, autotexts = ax.pie(
    acc_df["count"],
    labels=acc_df["verdict"],
    autopct="%1.0f%%",
    colors=colors_pie[:len(acc_df)],
    startangle=90,
    textprops={"fontsize": 11},
)
ax.set_title(f"BERTopic Label Accuracy vs Manual Annotation\n(n={total} sampled comments)",
             fontsize=12, fontweight="bold")
plt.tight_layout()
plt.savefig(FIG_DIR / "annotation_check.png", dpi=150, bbox_inches="tight")
plt.close()
print("Saved: figures/annotation_check.png")

print(f"\nAll outputs in: {OUT_DIR}")
