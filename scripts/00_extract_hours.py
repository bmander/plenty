"""Extract hours worked by industry from the BEA-BLS production account's underlying data.

Usage: python -I scripts/00_extract_hours.py <KLEMS-Research-Tables-Underlying-Data_0.xlsx> <out-dir>

The workbook is from https://www.bea.gov/products/integrated-industry-level-production-account-klems
("Underlying detailed data", 1947-2016). Only its last year is kept: for each of its 63 industries,
the hours worked, what labor was paid, and value added (gross output less intermediate inputs).
"""
import sys, pathlib
import openpyxl
import pandas as pd

src, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
rows = list(openpyxl.load_workbook(src, read_only=True, data_only=True)["1963-2016"].iter_rows(values_only=True))
x = pd.DataFrame([r for r in rows[2:] if r[0] is not None], columns=[str(c).strip(".") for c in rows[1]])
year = int(x.yr.max())
x = x[x.yr == year]
table = pd.DataFrame({"industry": x.indnum.astype(int), "name": x.Description, "hours_millions": x.hrs.round(3),
                      "labor_musd": (x.vlcol + x.vln).round(1), "value_added_musd": (x.go - x.ii).round(1)})
out.mkdir(parents=True, exist_ok=True)
table.to_csv(out / f"hours_{year}.csv", index=False)
print(f"hours_{year}.csv", table.shape, f"{table.hours_millions.sum() / 1e3:.1f} billion hours")
