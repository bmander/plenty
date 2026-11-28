"""Extract what each occupation does from the O*NET database to CSV.

Usage: python scripts/00_extract_tasks.py <db_31_0_csv.zip> <out-dir>

  db_31_0_csv.zip   O*NET 31.0 database, CSV edition (onetcenter.org/database.html)

Writes onet_tasks.csv (one row per occupation's task, with its importance, relevance and
frequency ratings), onet_task_activities.csv (the detailed work activities each task belongs
to) and onet_work_activities.csv (the three-level hierarchy of work activities). Columns are
trimmed and the rating scales are pivoted into columns; no values are changed.
"""
import sys, pathlib, zipfile
import pandas as pd

onet_zip, out = (pathlib.Path(a) for a in sys.argv[1:3])
out.mkdir(parents=True, exist_ok=True)
KEY = ["O*NET-SOC Code", "Task ID"]

with zipfile.ZipFile(onet_zip) as z:
    def read(name):
        hits = [n for n in z.namelist() if n.lower().endswith("/" + name)]
        if len(hits) != 1:
            raise SystemExit(f"{z.filename}: expected one member named {name}, found {hits}")
        return pd.read_csv(z.open(hits[0]))
    statements, ratings = read("task_statements.csv"), read("task_ratings.csv")
    to_dwa, hierarchy = read("tasks_to_dwas.csv"), read("gwas_to_iwas_to_dwas.csv")

def scale(s):
    return ratings[ratings["Scale ID"] == s].set_index(KEY)["Data Value"]

# FT is the percent of incumbents in each of seven frequency categories (yearly or less ... hourly or more)
freq = ratings[ratings["Scale ID"] == "FT"].pivot_table(index=KEY, columns="Category", values="Data Value")
freq.columns = [f"frequency_{int(c)}" for c in freq.columns]
tasks = (statements.set_index(KEY)[["Task", "Task Type"]]
         .join(scale("IM").rename("importance")).join(scale("RT").rename("relevance")).join(freq).reset_index()
         .rename(columns={"O*NET-SOC Code": "onet_soc", "Task ID": "task_id", "Task": "task", "Task Type": "task_type"}))
tasks.to_csv(out / "onet_tasks.csv", index=False)
print("onet_tasks.csv", tasks.shape)

links = (to_dwa[KEY + ["DWA Element ID"]].drop_duplicates()
         .rename(columns={"O*NET-SOC Code": "onet_soc", "Task ID": "task_id", "DWA Element ID": "dwa"}))
links.to_csv(out / "onet_task_activities.csv", index=False)
print("onet_task_activities.csv", links.shape)

hierarchy.columns = ["gwa", "gwa_name", "iwa", "iwa_name", "dwa", "dwa_name"]
hierarchy.to_csv(out / "onet_work_activities.csv", index=False)
print("onet_work_activities.csv", hierarchy.shape)
