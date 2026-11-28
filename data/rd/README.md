# Business R&D by industry

`berd_2017_rd_by_industry.csv` is table 17 of the NSF/NCSES Business Enterprise Research and
Development Survey, 2017: "Domestic R&D paid for by the company and others and performed by the
company as a percentage of domestic net sales, by industry and company size". Only the industry
rows are kept. Extracted with `scripts/00_extract_rd.py`; no values were changed. Downloaded
2026-11-24.

| | |
|---|---|
| Source | National Center for Science and Engineering Statistics, [NSF 20-311](https://ncses.nsf.gov/pubs/nsf20311), `nsf20311-tab017.xlsx` |
| Year | 2017, the same year as the BEA input-output tables |
| License | U.S. government work, public domain |

Columns: `industry`, `naics` (as published: ranges like `313–16`, lists, `other 333`), `rd_musd`
(domestic R&D performed by companies in the industry, all funders, $ millions), and BERD's two
intensity columns. Suppressed cells are kept as published: `D`, or a range such as
`1,376 - 1,475`, which `plenty/rd.py` reads as its midpoint.

How it is used (`plenty/rd.py`):

- Each BEA sector is matched, through the BEA-NAICS concordance in `../occupations/`, to the most
  specific BERD row covering its NAICS codes. "Other 333" rows take what their siblings do not;
  a parent row keeps only the R&D its matched children do not already account for.
- R&D intensity is the row's R&D over the BEA 2017 output of all sectors matched to it. BERD's
  own percentages divide by the sales of companies that perform or fund R&D, which overstates
  intensity where few do any (real estate shows 6.6%).
- 374 of 402 sectors are covered. BERD leaves out farms and government. $391 billion of the
  $400 billion total is mapped; electronic shopping ($9.3 billion) is lost because BEA's nonstore
  retail sector spans four NAICS codes, three of which BERD files under "other nonmanufacturing".
- BERD classifies a company by its main business, so a computer maker that designs in the United
  States and builds abroad has R&D close to its US output.
