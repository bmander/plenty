"""Extract the occupation data used for occupation-based capability usage to CSV.

Usage: python scripts/00_extract_occupations.py <db_31_0_csv.zip> <oesm21in4.zip> <MasterCrosswalk2017.rda> <out-dir>

  db_31_0_csv.zip         O*NET 31.0 database, CSV edition (onetcenter.org/database.html)
  oesm21in4.zip           OEWS May 2021 national industry-specific estimates (bls.gov/oes/tables.htm)
  MasterCrosswalk2017.rda BEA 2017 to NAICS 2017 crosswalk from USEPA/useeior (data/)

Columns are trimmed; values are not changed (OEWS suppression markers stay as text).
"""
import sys, pathlib, zipfile
import pandas as pd
import rdata

onet_zip, oews_zip, xwalk, out = (pathlib.Path(a) for a in sys.argv[1:5])
out.mkdir(parents=True, exist_ok=True)


def member(z: zipfile.ZipFile, contains: str, suffix: str) -> str:
    hits = [n for n in z.namelist() if contains in n.lower() and n.lower().endswith(suffix)]
    if len(hits) != 1:
        raise SystemExit(f"{z.filename}: expected one member like *{contains}*{suffix}, found {hits}")
    return hits[0]


with zipfile.ZipFile(onet_zip) as z:
    for src, dst in [("software_skills.csv", "onet_software_skills.csv"),
                     ("occupation_data.csv", "onet_occupations.csv")]:
        df = pd.read_csv(z.open(member(z, "/" + src, ".csv")))
        if dst == "onet_occupations.csv":
            df = df[["O*NET-SOC Code", "Title"]]
        df.to_csv(out / dst, index=False)
        print(dst, df.shape)

OEWS_COLS = ["NAICS", "NAICS_TITLE", "I_GROUP", "OWN_CODE", "OCC_CODE", "OCC_TITLE", "O_GROUP",
             "TOT_EMP", "A_MEAN"]
with zipfile.ZipFile(oews_zip) as z:
    df = pd.read_excel(z.open(member(z, "/nat4d_m", ".xlsx")), dtype=str)
    df.columns = [c.upper() for c in df.columns]
    df = df[OEWS_COLS]
    df.to_csv(out / "oews_2021_nat4d.csv", index=False)
    print("oews_2021_nat4d.csv", df.shape)

x = next(iter(rdata.read_rda(xwalk).values()))
x = x[["BEA_2017_Detail_Code", "NAICS_2017_Code"]].dropna().drop_duplicates()
x = x.rename(columns={"BEA_2017_Detail_Code": "bea_detail", "NAICS_2017_Code": "naics"})
x.sort_values(["bea_detail", "naics"]).to_csv(out / "bea_naics_2017.csv", index=False)
print("bea_naics_2017.csv", x.shape)
