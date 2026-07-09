"""
media_vs_public.py
==================
Compares topic distributions between comments on news media posts (新闻媒体)
vs. personal blogger posts (个人博主).

OUTPUT: data/processed/
  - media_vs_public.csv       — topic % for each account type
  - figures/media_vs_public.png
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

plt.rcParams["font.family"] = ["Arial Unicode MS", "PingFang SC", "Heiti TC", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

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

df = pd.read_csv(OUT_DIR / "comments_final.csv", encoding="utf-8-sig")
df = df[df["topic_id"] >= 0].copy()
df["theme"] = df["topic_id"].map(THEME_MAP)

# Keep only the two main account types
df = df[df["account_type"].isin(["新闻媒体", "个人博主"])].copy()
df["account_type"] = df["account_type"].map({"新闻媒体": "News Media\n(新闻媒体)", "个人博主": "Personal Blogger\n(个人博主)"})

pivot = (
    df.groupby(["account_type", "theme"])
      .size()
      .unstack(fill_value=0)
)
pivot_pct = pivot.div(pivot.sum(axis=1), axis=0) * 100

pivot_pct.to_csv(OUT_DIR / "media_vs_public.csv", encoding="utf-8-sig")

print("Topic % by account type:")
print(pivot_pct.round(1).to_string())
print()
for acct in pivot_pct.index:
    n = int(pivot.loc[acct].sum())
    print(f"  {acct.replace(chr(10),' ')}: n={n} comments")

# ── Figure ────────────────────────────────────────────────────────────────────

groups  = list(pivot_pct.index)
themes  = list(THEME_COLORS.keys())
x       = np.arange(len(groups))
width   = 0.13
offsets = np.linspace(-(len(themes)-1)/2, (len(themes)-1)/2, len(themes)) * width

fig, ax = plt.subplots(figsize=(11, 6))

for offset, theme in zip(offsets, themes):
    vals = [pivot_pct.loc[g, theme] if theme in pivot_pct.columns else 0 for g in groups]
    bars = ax.bar(x + offset, vals, width=width * 0.9,
                  color=THEME_COLORS[theme], label=theme,
                  edgecolor="white", linewidth=0.4)
    for bar, val in zip(bars, vals):
        if val >= 4:
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 0.5,
                    f"{val:.0f}%", ha="center", va="bottom",
                    fontsize=7.5, color="#333")

# n labels
for i, g in enumerate(groups):
    n = int(pivot.loc[g].sum())
    ax.text(i, ax.get_ylim()[1] * 0.97 if ax.get_ylim()[1] > 0 else 45,
            f"n={n}", ha="center", fontsize=9, color="#444")

ax.set_xticks(x)
ax.set_xticklabels(groups, fontsize=11)
ax.set_ylabel("% of comments (within group)", fontsize=11)
ax.set_title("Topic Distribution: Comments on News Media Posts vs. Personal Blogger Posts",
             fontsize=12, fontweight="bold", pad=12)
ax.spines[["top", "right"]].set_visible(False)
ax.legend(title="Theme", fontsize=8.5, title_fontsize=9,
          loc="upper right", framealpha=0.85)

plt.tight_layout()
plt.savefig(FIG_DIR / "media_vs_public.png", dpi=150, bbox_inches="tight")
plt.close()
print("\nSaved: figures/media_vs_public.png")
