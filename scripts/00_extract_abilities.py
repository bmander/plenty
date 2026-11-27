"""Extract O*NET's abilities to CSV: each occupation's ratings of them, and the general work
activities each ability is linked to.

Usage: python -I scripts/00_extract_abilities.py <db_31_0_csv.zip> <out-dir>

  db_31_0_csv.zip  O*NET 31.0 database, CSV edition (onetcenter.org/database.html)

Columns are trimmed and the two rating scales are pivoted into columns; values are not changed.
"""
import sys, pathlib, zipfile
import pandas as pd

onet_zip, out = (pathlib.Path(a) for a in sys.argv[1:3])
out.mkdir(parents=True, exist_ok=True)


def member(z: zipfile.ZipFile, name: str) -> str:
    hits = [n for n in z.namelist() if n.lower().endswith("/" + name)]
    if len(hits) != 1:
        raise SystemExit(f"{z.filename}: expected one member named {name}, found {hits}")
    return hits[0]


with zipfile.ZipFile(onet_zip) as z:
    a = pd.read_csv(z.open(member(z, "abilities.csv")))
    # one row for each occupation's rating of an ability: its importance (1 to 5) and the level of it needed (0 to 7)
    wide = (a.pivot_table(index=["O*NET-SOC Code", "Element ID", "Element Name"], columns="Scale ID", values="Data Value")
             .rename(columns={"IM": "importance", "LV": "level"}).reset_index()
             .rename(columns={"O*NET-SOC Code": "onet_soc", "Element ID": "ability", "Element Name": "ability_name"}))
    wide.columns.name = None
    wide[["onet_soc", "ability", "ability_name", "importance", "level"]].to_csv(out / "onet_abilities.csv", index=False)
    print("onet_abilities.csv", wide.shape)
    links = pd.read_csv(z.open(member(z, "abilities_to_work_activities.csv")))
    links.columns = ["ability", "ability_name", "gwa", "gwa_name"]
    links.to_csv(out / "onet_ability_activities.csv", index=False)
    print("onet_ability_activities.csv", links.shape)
