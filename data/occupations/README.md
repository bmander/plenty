# Occupation data

Inputs to the occupation-based measures (`plenty/occupations.py`, `plenty/work.py`, `plenty/flows.py`). Extracted with
`scripts/00_extract_occupations.py` and `scripts/00_extract_tasks.py`; columns are trimmed, the task rating scales are pivoted into columns, and no values were changed. Downloaded
2026-11-24.

| file | source | release | license |
|---|---|---|---|
| `onet_software_skills.csv` | O\*NET Resource Center, [O\*NET database](https://www.onetcenter.org/database.html), `db_31_0_csv.zip`, `software_skills.csv` | O\*NET 31.0, August 2026 (O\*NET-SOC 2019 taxonomy, SOC 2018 based) | [CC BY 4.0](https://www.onetcenter.org/license_db.html) |
| `onet_occupations.csv` | same, `occupation_data.csv` (code and title only) | O\*NET 31.0 | CC BY 4.0 |
| `onet_tasks.csv` | same, `task_statements.csv` joined with `task_ratings.csv`: one row per occupation's task, with its importance (1 to 5), relevance (percent of incumbents who do it) and the percent of incumbents in each of seven frequency categories | O\*NET 31.0 | CC BY 4.0 |
| `onet_task_activities.csv` | same, `tasks_to_dwas.csv`: the detailed work activities each task belongs to | O\*NET 31.0 | CC BY 4.0 |
| `onet_work_activities.csv` | same, `gwas_to_iwas_to_dwas.csv`: the hierarchy of general, intermediate and detailed work activities | O\*NET 31.0 | CC BY 4.0 |
| `oews_2021_nat4d.csv` | U.S. Bureau of Labor Statistics, [OEWS national industry-specific estimates](https://www.bls.gov/oes/tables.htm), `oesm21in4.zip`, `nat4d_M2021_dl.xlsx` | May 2021 (SOC 2018, NAICS 2017) | U.S. government work, public domain |
| `bea_naics_2017.csv` | `MasterCrosswalk2017` from [USEPA/useeior](https://github.com/USEPA/useeior) (`data/MasterCrosswalk2017.rda`), BEA 2017 detail code to NAICS 2017 at every level | useeior `master`, fetched 2026-11-24 | MIT (see `../bea/LICENSE-useeior`); the BEA concordance it encodes is public domain |

O\*NET 31.0 calls the technology file `software_skills.csv` and classifies each product with O\*NET's
own `Element Name` categories (e.g. "Computer aided design CAD software") instead of the UNSPSC
commodity codes used in releases before 30.

Notes on OEWS:

- **Year.** May 2021 is the first release fully on SOC 2018, which O\*NET uses, and the last on NAICS
  2017, which the BEA concordance uses. The input-output tables are 2017. Occupational mix within an
  industry moves slowly, but the four-year gap is a real mismatch.
- **Codes.** OEWS publishes some industries as aggregates: `3330A1` is "Machinery Manufacturing
  (3331, 3332, 3334, and 3339 only)", `327000` is the whole 3-digit industry. `oews_coverage()` reads
  which NAICS codes each one covers.
- **Markers.** `*` and `**` mean a wage or employment estimate is not available; those occupations
  are dropped. `#` means the annual wage is at or above $208,000 and is set to $208,000.
- **Coverage.** OEWS does not survey crop and animal production (NAICS 111, 112), private households
  or the self-employed. General government is published under 999xxx and has no BEA counterpart here.

O\*NET content is used under CC BY 4.0: "This page includes information from the O\*NET 31.0 Database
by the U.S. Department of Labor, Employment and Training Administration (USDOL/ETA). Used under the
CC BY 4.0 license. O\*NET® is a trademark of USDOL/ETA."
