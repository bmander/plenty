"""Extract two published tables about households to CSV: how people spend their time, and what
households at each level of income spend their money on.

Usage: python -I scripts/00_extract_households.py <atus_a1_2017.pdf> <cex_quintiles_2017.xlsx> <out-dir>

  atus_a1_2017.pdf          U.S. Bureau of Labor Statistics, American Time Use Survey, 2017, Table A-1
                            (bls.gov/tus/tables/a1_2017.pdf). Read with pdftotext, which must be installed.
  cex_quintiles_2017.xlsx   U.S. Bureau of Labor Statistics, Consumer Expenditure Survey, 2017, Table 1101,
                            quintiles of income before taxes (bls.gov/cex/tables/calendar-year/
                            mean-item-share-average-standard-error/cu-income-quintiles-before-taxes-2017.xlsx)

Rows and columns are selected; no values are changed. See data/households/README.md for what is kept.
"""
import pathlib, re, subprocess, sys
import openpyxl
import pandas as pd

atus_pdf, cex_xlsx, out = (pathlib.Path(a) for a in sys.argv[1:4])
out.mkdir(parents=True, exist_ok=True)

# Time use: each activity's average hours a day, for the civilian population of 15 and over. A line
# of the table is a name, a row of dots, then nine figures; a long name runs over two lines. An
# estimate printed as a dash and a footnote number is approximately zero, or suppressed.
text = subprocess.run(["pdftotext", "-layout", str(atus_pdf), "-"], check=True, capture_output=True, text=True).stdout
line = re.compile(r"^\s*(?P<name>.*?\S)\s*(?:\.\s?){3,}\s*(?P<hours>\d+\.\d+|[–-]\d)\s")
rows, carried = [], ""
for raw in text.splitlines():
    m = line.match(raw)
    if m:
        name = re.sub(r"(?<=[a-z])\d$", "", (carried + " " + m["name"]).strip())      # a footnote mark is not part of the name
        hours = m["hours"]
        rows.append({"activity": name, "hours_per_day": float(hours) if hours[0].isdigit() else 0.0})
        carried = ""
    elif raw.startswith("  ") and raw.strip() and not re.search(r"\d\s*$|Average|Activity|Total +Men|footnotes", raw):
        carried = (carried + " " + raw.strip()).strip()                                 # the first line of a long name
    else:
        carried = ""
t = pd.DataFrame(rows)
t.insert(0, "line", range(1, len(t) + 1))
assert t.activity[0].startswith("Total, all activities") and t.hours_per_day[0] == 24.0, t.head()
t.to_csv(out / "time_use_2017.csv", index=False)
print("time_use_2017.csv", t.shape)

# Spending: the mean a year for all consumer units and for each fifth of them by income, item by
# item, down to the end of the table of expenditures; and the lines that say how many units and
# people there are.
ws = openpyxl.load_workbook(cex_xlsx, data_only=True).worksheets[0]
cells = [[c for c in r] for r in ws.iter_rows(values_only=True)]
cols = ["all", "lowest", "second", "third", "fourth", "highest"]
rows, item = [], None
for r in cells:
    label = (r[0] or "").strip() if isinstance(r[0], str) else ""
    figures = list(r[1:7])
    if label.startswith("Sources of income"):
        break
    if label in ("Number of consumer units (in thousands)", "People", "Children under 18"):
        rows.append({"item": label, **dict(zip(cols, figures))})
    elif label == "Mean" and item:
        rows.append({"item": item, **dict(zip(cols, figures))})
    elif label and all(x in (None, "") for x in figures):
        item = label
s = pd.DataFrame(rows)
s = s[pd.to_numeric(s["all"], errors="coerce").notna()]
assert not s.item.duplicated().any(), s.item[s.item.duplicated()].tolist()
s.to_csv(out / "spending_quintiles_2017.csv", index=False)
print("spending_quintiles_2017.csv", s.shape)
