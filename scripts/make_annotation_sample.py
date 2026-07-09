"""
make_annotation_sample.py
=========================
Generates two annotation files:

1. incident_coding_prefilled.csv  — incident-level mental illness coding,
   pre-filled where confidently inferrable from incident name / BERTopic patterns.
   YOU fill in the remaining rows.

2. comment_annotation_sample.csv  — stratified sample of ~150 comments
   (across all 6 BERTopic themes) ready for manual topic validation.

OUTPUT: data/raw/
"""

from pathlib import Path
import pandas as pd

BASE = Path(__file__).parent.parent

# ── 1. Incident-level coding ──────────────────────────────────────────────────

PREFILLED = {
    # confirmed: incident name or dominant BERTopic pattern makes it unambiguous
    "红谷滩杀人事件":                              ("confirmed", "Topic 0 dominates (80%+); comments explicitly dispute mental illness defense"),
    "成都女子遇害案":                              ("confirmed", "Topic 0 dominates (80%+); perpetrator officially diagnosed"),
    "2021中南财经政法大学副教授被精神病人杀害案":  ("confirmed", "Incident name states perpetrator was mentally ill"),
    "广州宝马撞人案":                              ("alleged",   "Comments mention mental illness claim; verify official diagnosis"),

    # none: school/child attacks or nationalist framing — no mental illness discourse
    "深圳日本人学校学生被刺":                      ("none",      "Topic 22 (nationalist framing) dominates; no mental illness discourse"),
    "江西一男子幼儿园行凶":                        ("none",      "Topics 1/3 (child victims) dominate; no mental illness framing in comments"),
    "廉江幼儿园行凶事件":                          ("none",      "Topics 1/3 (child victims) dominate"),
    "广西梧州旺甫小学保安持刀伤人":               ("none",      "School security topic; no mental illness framing"),
    "湖北恩施涉校刑事案件":                        ("none",      "School-related; verify"),
    "贵溪小学持刀伤人":                            ("none",      "School attack; verify"),
    "米脂县中学砍人案":                            ("none",      "School attack; verify"),
    "2010年4月福建南平校园惨案":                   ("none",      "School attack; verify"),

    # unclear: vehicle rammings where mental state is contested or unknown
    "景德镇一家三口被撞":                          ("unclear",   "Topic 14 (sentencing); mental illness claim contested — verify"),
    "珠海男子驾驶汽车撞倒多名行人":               ("unclear",   "Vehicle ramming; motive unclear — verify"),
    "德州男子故意冲撞":                            ("unclear",   "Vehicle ramming; verify"),
    "常德撞人事件":                                ("unclear",   "Vehicle ramming; verify"),
    "北京密云撞人":                                ("unclear",   "Vehicle ramming; verify"),
}

coding = pd.read_csv(BASE / "data/raw/incident_coding.csv", encoding="utf-8-sig")
coding["mental_illness"] = coding["incident"].map(lambda x: PREFILLED.get(x, ("", ""))[0])
coding["notes"]          = coding["incident"].map(lambda x: PREFILLED.get(x, ("", ""))[1])

out_path = BASE / "data/raw/incident_coding_prefilled.csv"
coding.to_csv(out_path, index=False, encoding="utf-8-sig")
print(f"Saved: {out_path}")
print(f"  Pre-filled: {(coding['mental_illness'] != '').sum()} / {len(coding)} incidents")
print(f"  Still need: {(coding['mental_illness'] == '').sum()} incidents\n")


# ── 2. Comment-level annotation sample ───────────────────────────────────────

THEME_MAP = {
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

BERT_LABELS = {
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

df = pd.read_csv(BASE / "data/processed/comments_with_topics.csv", encoding="utf-8-sig")
df = df[df["topic_id"] >= 0].copy()
df["theme"]       = df["topic_id"].map(THEME_MAP)
df["bert_label"]  = df["topic_id"].map(BERT_LABELS)

# Stratified sample: ~25 comments per theme (6 themes × 25 = 150)
# Within each theme, sample proportionally from its topics, sorted by likes desc
SAMPLES_PER_THEME = 25
frames = []
for theme, group in df.groupby("theme"):
    n = min(SAMPLES_PER_THEME, len(group))
    sampled = group.sort_values("likes", ascending=False).head(n * 3).sample(n, random_state=42)
    frames.append(sampled)

sample = pd.concat(frames).sort_values(["theme", "topic_id", "likes"], ascending=[True, True, False])
sample = sample.reset_index(drop=True)
sample.index += 1  # 1-based row numbers

out_cols = [
    "incident", "text", "likes",
    "topic_id", "bert_label", "theme",
    "comment_id",
]
sample = sample[out_cols].copy()

# Add blank columns for manual annotation
sample["manual_theme"]             = ""   # fill in: which of the 6 themes does this belong to?
sample["mental_illness_mentioned"] = ""   # fill in: yes / no
sample["sentiment_toward_mi_defense"] = ""  # fill in: skeptical / supportive / neutral / n/a
sample["bert_correct"]             = ""   # fill in: yes / no / partial
sample["notes"]                    = ""

out_path2 = BASE / "data/raw/comment_annotation_sample.csv"
sample.to_csv(out_path2, encoding="utf-8-sig")
print(f"Saved: {out_path2}")
print(f"  Total comments sampled: {len(sample)}")
print(f"  Breakdown by theme:")
for theme, grp in sample.groupby("theme"):
    print(f"    {theme}: {len(grp)}")

print("\nDone. Open these files in Excel or Google Sheets to annotate.")
print("Columns to fill in:")
print("  incident_coding_prefilled.csv → mental_illness (confirmed/alleged/none/unclear)")
print("  comment_annotation_sample.csv → manual_theme, mental_illness_mentioned,")
print("                                   sentiment_toward_mi_defense, bert_correct, notes")
