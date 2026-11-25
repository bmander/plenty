"""Extract business R&D by industry (NSF/NCSES BERD 2017, table 17) to CSV.

Usage: python scripts/00_extract_rd.py <nsf20311-tab017.xlsx> <out-dir>

Keeps the industry rows (not the company-size rows) with their NAICS codes and domestic R&D
performed by the company, all funders, in $ millions. Values are unchanged: suppressed cells
stay as published ('D', or a range such as '1,376 - 1,475').
"""
import sys, pathlib
import pandas as pd

src, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
t = pd.read_excel(src, header=None, dtype=str)
head = t.index[t[0].str.strip().eq("Industry and company size")][0]
end = t.index[t[0].str.startswith("All companies (number of domestic employees)", na=False)][0]
rows = t.iloc[head + 1:end, [0, 1, 2, 4, 6]]
rows.columns = ["industry", "naics", "rd_musd", "pct_sales_performers_or_funders", "pct_sales_performers"]
rows = rows.apply(lambda c: c.str.strip())
rows.to_csv(out / "berd_2017_rd_by_industry.csv", index=False)
print(rows.shape)
