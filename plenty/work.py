"""The work that has to get done: O*NET's work activities, and the tasks that make them up.

Software, AI or a person with a pencil are means. This is the layer above them: what each
occupation does, in O*NET's own words, grouped by O*NET's three-level hierarchy of work
activities (41 general, 332 intermediate, 2,087 detailed).

    share[t]    = importance[t] * relevance[t] / sum over the occupation's tasks
    theta[o, d] = sum of share[t] / (activities t belongs to), over o's tasks t in activity d

importance is the task's rated importance to the occupation (1 to 5) and relevance the share
of incumbents who say they do it. Neither is time: O*NET does not record hours per task. The
frequency variant weights a task by how often it is done instead, which tells much the same
story (see the sensitivity row written by scripts/03_run.py).

flows.flow() then carries each need dollar through sectors and occupations to activities, the
same way it carries it to software capabilities, and joint() splits that flow by the software
the same occupations list.
"""
from __future__ import annotations
import pandas as pd
from . import occupations as O

# Occurrences a year assumed for O*NET's seven frequency categories (yearly or less, more than
# yearly, more than monthly, more than weekly, daily, several times daily, hourly or more).
# Used only for the frequency variant.
PER_YEAR = {1: 1, 2: 4, 3: 24, 4: 104, 5: 260, 6: 780, 7: 2080}
WEIGHTS = ("importance", "frequency")


def hierarchy() -> pd.DataFrame:
    """Detailed work activity -> its name and its intermediate and general activities."""
    return pd.read_csv(O.OCC / "onet_work_activities.csv").set_index("dwa")


def tasks() -> pd.DataFrame:
    """One row per occupation's task with its two weights. A task O*NET has not rated yet takes
    the mean of its occupation's rated tasks; occupations with no rated task are dropped."""
    t = pd.read_csv(O.OCC / "onet_tasks.csv")
    t["importance"] = t.importance * t.relevance / 100
    t["frequency"] = sum(t[f"frequency_{c}"] / 100 * n for c, n in PER_YEAR.items())
    for c in WEIGHTS:
        t[c] = t[c].fillna(t.groupby("onet_soc")[c].transform("mean"))
    t = t.dropna(subset=list(WEIGHTS))
    return t.assign(soc=O.soc6(t.onet_soc))[["soc", "onet_soc", "task_id", "task", *WEIGHTS]]


def task_activity_shares(t: pd.DataFrame, weight: str = "importance") -> pd.DataFrame:
    """(soc, onet_soc, task_id, task, dwa, share): each task's share of its SOC occupation's
    work, divided among the detailed activities it belongs to. Shares sum to 1 per SOC code:
    a task's share is taken within its detailed O*NET occupation, and the detailed occupations
    under one SOC code count equally."""
    links = pd.read_csv(O.OCC / "onet_task_activities.csv")
    within = t[weight] / t.groupby("onet_soc")[weight].transform("sum")
    x = t.assign(share=within / t.groupby("soc").onet_soc.transform("nunique")).merge(links, on=["onet_soc", "task_id"])
    x["share"] = x.share / x.groupby(["onet_soc", "task_id"]).dwa.transform("size")
    return x[["soc", "onet_soc", "task_id", "task", "dwa", "share"]]


def occupation_activity_shares(shares: pd.DataFrame) -> pd.DataFrame:
    """theta: SOC x detailed work activity. Rows sum to 1."""
    return shares.groupby(["soc", "dwa"]).share.sum().unstack(fill_value=0.0)


def soc_value(occupation_value: pd.Series, socs: pd.Index) -> pd.Series:
    """Share of the basket's value added earned in each SOC occupation. OEWS reports some
    occupations as an aggregate code ending in 0; its value is divided equally among the SOC
    codes under it, which is what taking their mean share does in occupations.shares."""
    out = pd.Series(0.0, index=socs)
    for code, v in occupation_value.items():
        if code in out.index:
            out[code] += v
        else:
            members = socs[socs.str.startswith(code.rstrip("0"))]
            if len(members):
                out[members] += v / len(members)
    return out


def joint(value: pd.Series, activity_shares: pd.DataFrame, capability_shares: pd.DataFrame) -> pd.DataFrame:
    """Activity x capability: the value flowing through each activity, split by the software
    the same occupations list. It assumes an occupation's software is spread over its
    activities evenly: O*NET says which software an occupation uses, not what for."""
    socs = activity_shares.index.intersection(capability_shares.index)
    a, c = activity_shares.loc[socs], capability_shares.loc[socs]
    return a.mul(value.reindex(socs).fillna(0.0), axis=0).T @ c
