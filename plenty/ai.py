"""AI as a means: what three AI vendors report their systems being used for, by work activity.

Software capabilities are one means of doing the work in plenty/work.py; AI systems are another.
Nothing here measures how well AI does an activity. It records where AI is used, from each
vendor's own published classification of its conversations into O*NET work activities:

  claude       Anthropic Economic Index (June 2026 release): Claude chat conversations in the
               United States, April and May 2026, restricted to work use
  claude_api   the same release: Anthropic API traffic, worldwide (Claude Code excluded)
  chatgpt      OpenAI Signals v3.0: work-related consumer ChatGPT messages in the United States,
               the four quarters to September 2026
  copilot      Microsoft "Working with AI": Bing Copilot conversations in the United States,
               January to September 2024, by the user's goal (copilot_action: by what the AI did)

Each is a share of that source's conversations, so each column sums to at most 1. pooled is the
mean of claude, chatgpt and copilot: three vendors' chat products, counted equally. An activity
a source does not publish (too few conversations) counts as zero there.
"""
from __future__ import annotations
import pandas as pd
from . import model as M, work as W

AI = M.ROOT / "data" / "ai"
SOURCES = ("claude", "chatgpt", "copilot")       # the three chat products pooled
LEVELS = {"detailed": (1, "dwa"), "intermediate": (2, "iwa"), "general": (3, "gwa")}
OPENAI_QUARTERS = 4                              # most recent quarters averaged


def _ids(level: str) -> pd.Series:
    """Activity name -> this project's O*NET 31.0 id, at one level of the hierarchy."""
    col = LEVELS[level][1]
    h = W.hierarchy().reset_index()
    return h.drop_duplicates(col).set_index(f"{col}_name")[col]


def legacy_iwa_ids() -> pd.Series:
    """The older intermediate-activity ids OpenAI and Microsoft use (4.A.1.a.1.I01) -> this
    project's ids, through the activity names Microsoft's file carries beside them."""
    m = pd.read_csv(AI / "microsoft_iwa_metrics.csv")
    return pd.Series(m.title.map(_ids("intermediate")).values, index=m.IWA)


def anthropic(level: str = "intermediate") -> pd.DataFrame:
    """Per activity: claude and claude_api shares, and Anthropic's descriptions of how Claude
    chat is used for it worldwide (automation share, autonomy, time with and without AI).

    claude is the share of United States conversations in the activity times the share of
    that activity's conversations that are work (published worldwide only), rescaled to the
    same total, so that coursework and personal use are set aside."""
    a = pd.read_csv(AI / "anthropic_onet.csv")
    a = a[a.hierarchy_level == LEVELS[level][0]].assign(activity=lambda d: d.node_name.map(_ids(level)))
    if a.activity.isna().any():
        raise ValueError(f"Anthropic activities not in O*NET {level}: {sorted(a.node_name[a.activity.isna()].unique())[:5]}")
    # mean over the months published; a month with no row for a cell is a month it was not published
    v = a.groupby(["source", "geo_id", "metric_id", "activity"]).value.mean()
    def get(source, geo, metric):
        return v.get((source, geo, metric), pd.Series(dtype=float))
    out = pd.DataFrame(index=sorted(set(a.activity)))
    us, work = get("claude_ai", "USA", "pct") / 100, get("claude_ai", "GLOBAL", "use_case_work_pct") / 100
    at_work = (us * work.reindex(us.index)).dropna()
    out["claude"] = at_work * us.sum() / at_work.sum()
    out["claude_api"] = get("1p_api", "GLOBAL", "pct") / 100
    out["automation"] = get("claude_ai", "GLOBAL", "collaboration_bucket_automation_pct") / 100
    out["autonomy"] = get("claude_ai", "GLOBAL", "ai_autonomy_mean")
    out["hours_without_ai"] = get("claude_ai", "GLOBAL", "human_only_time_mean")
    out["minutes_with_ai"] = get("claude_ai", "GLOBAL", "human_with_ai_time_mean")
    return out


def openai() -> tuple[pd.Series, float]:
    """(share of work-related ChatGPT messages by intermediate activity, share OpenAI reports
    only as 'Other IWA'), averaged over the most recent quarters."""
    o = pd.read_csv(AI / "openai_iwa_us.csv")
    o = o[o.quarter.isin(sorted(o.quarter.unique())[-OPENAI_QUARTERS:])]
    s = o.groupby("iwa_cleaned").share_of_messages.mean()
    other = float(s.get("Other IWA", 0.0))
    s = s.drop("Other IWA", errors="ignore")
    ids = legacy_iwa_ids()
    if not set(s.index) <= set(ids.index):
        raise ValueError(f"OpenAI activities not recognised: {sorted(set(s.index) - set(ids.index))[:5]}")
    return s.rename(index=ids), other


def microsoft() -> pd.DataFrame:
    """Per intermediate activity: copilot (share of conversations with this as the user's
    goal), copilot_action (as what the AI did), and for conversations where the AI did it, how
    often it completed the task and how often its help was moderate or larger in scope."""
    m = pd.read_csv(AI / "microsoft_iwa_metrics.csv")
    m = m.set_index(m.IWA.map(legacy_iwa_ids()))
    return pd.DataFrame({"copilot": m.share_user, "copilot_action": m.share_ai,
                         "copilot_completion": m.completion_ai, "copilot_scope": m.impact_scope_ai})


def use() -> pd.DataFrame:
    """One row per intermediate work activity (all 332): each source's share and the pooled share."""
    iwas = sorted(W.hierarchy().iwa.unique())
    out = anthropic().reindex(iwas).join(openai()[0].rename("chatgpt")).join(microsoft())
    shares = ["claude", "claude_api", "chatgpt", "copilot", "copilot_action"]
    out[shares] = out[shares].fillna(0.0)
    out["pooled"] = out[list(SOURCES)].mean(axis=1)
    return out.rename_axis("activity")
