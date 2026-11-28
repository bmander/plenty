"""Extract hours worked by industry from the BEA-BLS production account's underlying data.

Usage: python -I scripts/00_extract_hours.py <KLEMS-Research-Tables-Underlying-Data_0.xlsx> <out-dir>

The workbook is from https://www.bea.gov/products/integrated-industry-level-production-account-klems
("Underlying detailed data", 1947-2016). Two files are written. hours_<last year>.csv has, for each
of its 63 industries in its last year, the hours worked, what labor was paid, and value added (gross
output less intermediate inputs). production_account_<since>_<last year>.csv has, for each industry
and year from SINCE on, the hours worked, gross output and intermediate inputs in dollars, and the
quantity index of each: what is needed to say how the hours behind a unit of real output have moved.
"""
import sys, pathlib
import openpyxl
import pandas as pd

src, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
rows = list(openpyxl.load_workbook(src, read_only=True, data_only=True)["1963-2016"].iter_rows(values_only=True))
x = pd.DataFrame([r for r in rows[2:] if r[0] is not None], columns=[str(c).strip(".") for c in rows[1]])
SINCE = 1987
year = int(x.yr.max())
series = x[x.yr >= SINCE]
series = pd.DataFrame({"industry": series.indnum.astype(int), "year": series.yr.astype(int), "hours_millions": series.hrs.round(3),
                       "gross_output_musd": series.go.round(1), "intermediate_musd": series.ii.round(1),
                       "gross_output_quantity": series.goqi.round(6), "intermediate_quantity": series.iiqi.round(6)})
x = x[x.yr == year]
table = pd.DataFrame({"industry": x.indnum.astype(int), "name": x.Description, "hours_millions": x.hrs.round(3),
                      "labor_musd": (x.vlcol + x.vln).round(1), "value_added_musd": (x.go - x.ii).round(1)})
out.mkdir(parents=True, exist_ok=True)
table.to_csv(out / f"hours_{year}.csv", index=False)
print(f"hours_{year}.csv", table.shape, f"{table.hours_millions.sum() / 1e3:.1f} billion hours")
series.to_csv(out / f"production_account_{SINCE}_{year}.csv", index=False)
print(f"production_account_{SINCE}_{year}.csv", series.shape)
