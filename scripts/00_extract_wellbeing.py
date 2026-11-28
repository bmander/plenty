"""Extract how people felt during each kind of activity from the American Time Use Survey's Well-Being Module.

Usage: python -I scripts/00_extract_wellbeing.py <folder> <out-dir>

<folder> holds the Bureau of Labor Statistics's archives, each in a folder of its own, from
https://www.bls.gov/tus/datafiles/: the module's activity files (wbact_1013.zip for 2010, 2012 and
2013, wbact-2021.zip) and the survey's activity files for the same years (atusact_2010.zip,
atusact_2012.zip, atusact_2013.zip, atusact-2021.zip), which say what each rated activity was.

Written: wellbeing_by_activity.csv, one row for each six-digit activity code that was rated. Each
respondent rated three of the day's activities from 0 to 6 on six feelings. A row has the number
of ratings, its share of all the rated time, the mean of each feeling, and the share of the time
that was unpleasant: when pain, sadness or stress was rated above happiness. Means are weighted by
the module's activity weights, which count an activity by the time it took.

It also has the activity on one scale from 0 to 10, points: happiness less the mean of pain,
sadness and stress, which runs from -6 to 6, moved and stretched to run from 0 to 10. severe is
the share of the time when pain, sadness or stress was rated 5 or 6. below_rest is how many points
the activity was rated below the same person's other rated time that was not work: not working at
a job, and not one of the kinds of unpaid work in config/unpaid_work.csv. compared is the number
of ratings that could be compared so, and compared_time their share of all the rated time.
"""
import sys, pathlib, zipfile
import pandas as pd

src, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
FEELINGS = {"WUHAPPY": "happy", "WUMEANING": "meaningful", "WUPAIN": "pain", "WUSAD": "sad", "WUSTRESS": "stress", "WUTIRED": "tired"}
MODULE = {"wbact_1013": "WUFNACTWTC", "wbact-2021": "WUFNACTWT"}      # the archive, and its weight (2010 to 2013: the one adjusted for an error in selection)
DIARIES = ["atusact_2010", "atusact_2012", "atusact_2013", "atusact-2021"]
BAD = ["pain", "sad", "stress"]
SEVERE = 5                 # a rating of this or more, of 6
JOB = "0501"               # the survey's code for working at a job
UNPAID = pathlib.Path(__file__).resolve().parent.parent / "config" / "unpaid_work.csv"      # and the codes of unpaid work at home


def table(folder: str) -> pd.DataFrame:
    archive = zipfile.ZipFile(next((src / folder).glob("*.zip")))
    name = next(n for n in archive.namelist() if n.endswith(".dat"))
    return pd.read_csv(archive.open(name), dtype={"TUCASEID": str, "TRCODE": str}, low_memory=False)


rated = pd.concat([table(folder).rename(columns={weight: "weight"})[["TUCASEID", "TUACTIVITY_N", "weight", *FEELINGS]]
                   for folder, weight in MODULE.items()])
diaries = pd.concat([table(folder)[["TUCASEID", "TUACTIVITY_N", "TRCODE"]] for folder in DIARIES])
x = rated.merge(diaries, on=["TUCASEID", "TUACTIVITY_N"], how="left", validate="one_to_one")
assert x.TRCODE.notna().all(), "a rated activity is not in the diaries"
x = x[(x[list(FEELINGS)] >= 0).all(axis=1) & (x.weight > 0)].rename(columns=FEELINGS)       # a negative rating is one not given
x["code"] = x.TRCODE.str.zfill(6)
x["unpleasant"] = (x[BAD].max(axis=1) > x.happy).astype(float)
x["points"] = (x.happy - x[BAD].mean(axis=1) + 6) / 12 * 10
x["severe"] = (x[BAD].max(axis=1) >= SEVERE).astype(float)
# each rating against the same person's other rated time that was not work
work = (JOB, *(c for codes in pd.read_csv(UNPAID, dtype=str).time_use_codes for c in codes.split(";")))
rest = ~x.code.str.startswith(work)
other_time = (x.weight * rest).groupby(x.TUCASEID).transform("sum") - x.weight * rest
other_points = (x.points * x.weight * rest).groupby(x.TUCASEID).transform("sum") - x.points * x.weight * rest
c = x[other_time > 0].assign(below_rest=lambda c: other_points[c.index] / other_time[c.index] - c.points)
measures = [*FEELINGS.values(), "unpleasant", "points", "severe"]
by = x.groupby("code")
weight, compared = by.weight.sum(), c.groupby("code").weight.sum()
t = pd.DataFrame({"ratings": by.size(), "share_of_time": (weight / weight.sum()).round(6),
                  **{m: (x[m] * x.weight).groupby(x.code).sum().div(weight).round(4) for m in measures},
                  "compared": c.groupby("code").size(), "compared_time": (compared / weight.sum()).round(6),
                  "below_rest": (c.below_rest * c.weight).groupby(c.code).sum().div(compared).round(4)})
t = t.fillna({"compared": 0, "compared_time": 0.0}).astype({"compared": int})
out.mkdir(parents=True, exist_ok=True)
t.to_csv(out / "wellbeing_by_activity.csv")
print("wellbeing_by_activity.csv", t.shape, f"{len(x):,} ratings; unpleasant {(x.unpleasant * x.weight).sum() / x.weight.sum():.3f} of the time; "
      f"{len(c):,} compared; a job {(c.below_rest * c.weight)[c.code.str.startswith(JOB)].sum() / c.weight[c.code.str.startswith(JOB)].sum():.2f} points below the rest")
