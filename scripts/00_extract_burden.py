"""Extract the burden of disease in the United States from the World Health Organization's Global Health Estimates.

Usage: python -I scripts/00_extract_burden.py <folder> <out-dir>

<folder> holds two of the Organization's spreadsheets for 2019, each in a folder of its own, from
https://www.who.int/data/gho/data/themes/mortality-and-global-health-estimates/global-health-estimates-leading-causes-of-dalys:
years lived with disability (yld/yld_bycountry_age_sex_2019.xlsx) and years of life lost
(yll/yll_bycountry_age_sex_2019.xlsx), by cause and country.

Written: burden_2019.csv, one row for each cause in the Organization's list, in its order: the cause's
code and name, how deep it is in the list (0 is all causes), the code of the cause it is filed under,
whether nothing is filed under it, and the thousands of years lived with disability and of life lost
in the United States in 2019, by people of both sexes and all ages.
"""
import sys, pathlib
import openpyxl
import pandas as pd

src, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
COUNTRY, SHEET, SEX = "USA", "All ages", "Persons"


def table(folder: str) -> pd.DataFrame:
    sheet = openpyxl.load_workbook(next((src / folder).glob("*.xlsx")), read_only=True)[SHEET]
    sheet.reset_dimensions()                                       # the file understates its own size
    rows = list(sheet.iter_rows(values_only=True))
    codes = next(r for r in rows if COUNTRY in r)                  # the row of countries' three-letter codes
    at = codes.index(COUNTRY)
    found = []
    for r in rows:
        if r[0] != SEX or r[1] in (None, ""):                      # the population has no code
            continue
        named = max(i for i in range(2, 7) if r[i] not in (None, ""))
        found.append({"code": str(r[1]).strip(), "cause": str(r[named]).strip(),
                      "level": named - 2 if r[named - 1] not in (None, "") else 0, "thousands": float(r[at] or 0)})
    return pd.DataFrame(found)


yld, yll = table("yld"), table("yll")
assert list(yld.code) == list(yll.code) and list(yld.cause) == list(yll.cause) and yld.code.is_unique
t = yld.rename(columns={"thousands": "yld_thousands"}).assign(yll_thousands=yll.thousands)
above, parents = {}, []
for r in t.itertuples():                                           # a cause is filed under the last one above it that is less deep
    parents.append(above.get(r.level - 1, ""))
    above[r.level] = r.code
t.insert(3, "under", parents)
t.insert(4, "last", [i + 1 == len(t) or t.level[i + 1] <= t.level[i] for i in range(len(t))])
out.mkdir(parents=True, exist_ok=True)
t.round({"yld_thousands": 3, "yll_thousands": 3}).to_csv(out / "burden_2019.csv", index=False)
whole, parts = t[t.level == 0].iloc[0], t[t["last"]]
print("burden_2019.csv", t.shape, f"all causes: {whole.yld_thousands / 1e3:,.1f} million years lived with disability, "
      f"{whole.yll_thousands / 1e3:,.1f} million of life lost; the {len(parts)} causes with nothing under them come to "
      f"{parts.yld_thousands.sum() / 1e3:,.1f} and {parts.yll_thousands.sum() / 1e3:,.1f}")
