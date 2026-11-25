"""Extract published data on what AI systems are used for, by O*NET work activity, to CSV.

Usage: python -I scripts/00_extract_ai.py <aei_claude_ai.csv> <aei_1p_api.csv> <openai-signals.zip> <iwa_metrics.csv> <out-dir>

  aei_claude_ai.csv, aei_1p_api.csv   Anthropic Economic Index, release_2026_06_26/data
                                      (huggingface.co/datasets/Anthropic/EconomicIndex)
  openai-signals.zip                  OpenAI Signals v3.0, data-download-csv.zip (openai.com/signals/data-download)
  iwa_metrics.csv                     Microsoft "Working with AI" (github.com/microsoft/working-with-ai)

Rows and columns are selected; no values are changed. See data/ai/README.md for what is kept.
"""
import io, sys, pathlib, zipfile
import pandas as pd

claude_csv, api_csv, openai_zip, ms_csv, out = (pathlib.Path(a) for a in sys.argv[1:6])
out.mkdir(parents=True, exist_ok=True)

# Anthropic: the O*NET work-activity rows (detailed, intermediate and general activities), for the
# world and, where published, the United States, and the metrics this project reads.
METRICS = ["pct", "use_case_work_pct", "collaboration_bucket_automation_pct", "collaboration_bucket_augmentation_pct",
           "ai_autonomy_mean", "human_only_time_mean", "human_with_ai_time_mean"]
frames = []
for source, path in (("claude_ai", claude_csv), ("1p_api", api_csv)):
    d = pd.read_csv(path, dtype={"node_external_id": str})
    d = d[(d.category_name == "onet") & d.geo_id.isin(["GLOBAL", "USA"]) & d.hierarchy_level.isin([1, 2, 3]) & d.metric_id.isin(METRICS)]
    frames.append(d.assign(source=source)[["source", "date_start", "date_end", "geo_id", "hierarchy_level", "metric_id",
                                           "value", "node_name", "node_external_id"]])
a = pd.concat(frames).sort_values(["source", "geo_id", "date_start", "hierarchy_level", "node_external_id", "metric_id"])
a.to_csv(out / "anthropic_onet.csv", index=False)
print("anthropic_onet.csv", a.shape)

# OpenAI: work-related ChatGPT messages by intermediate work activity, United States rows.
with zipfile.ZipFile(openai_zip) as z:
    name = [n for n in z.namelist() if n.endswith("share_of_work_related_messages_by_onet_iwa_country_quarter.csv")]
    if len(name) != 1:
        raise SystemExit(f"{openai_zip}: expected one IWA file, found {name}")
    o = pd.read_csv(io.BytesIO(z.read(name[0])))
o = o[o.country == "US"]
o.to_csv(out / "openai_iwa_us.csv", index=False)
print("openai_iwa_us.csv", o.shape)

# Microsoft: the whole file (332 intermediate work activities).
m = pd.read_csv(ms_csv)
m.to_csv(out / "microsoft_iwa_metrics.csv", index=False)
print("microsoft_iwa_metrics.csv", m.shape)
