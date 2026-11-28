# Health

| File | Source | What it is | Licence |
|---|---|---|---|
| `burden_2019.csv` | World Health Organization, Global Health Estimates 2023: Disease burden by Cause, Age, Sex, by Country and by Region, 2000-2023 (Geneva, 2026), the [by-country files for 2019](https://www.who.int/data/gho/data/themes/mortality-and-global-health-estimates/global-health-estimates-leading-causes-of-dalys): `yld_bycountry_age_sex_2019` and `yll_bycountry_age_sex_2019`. Extracted with `scripts/00_extract_burden.py`, downloaded 2026-11-27 | For each cause in the Organization's list, in its order: the code, the name, how deep it is in the list, the code of the cause it is filed under, whether nothing is filed under it, and the thousands of years lived with disability and of years of life lost in the United States in 2019, both sexes and all ages. | World Health Organization, CC BY-NC-SA 3.0 IGO |

## Notes

- **A year lived with disability** is a year lived with a cause, counted for the part of full
  health the cause takes. **A year of life lost** is a year short of a standard length of life.
  Their sum is what the Organization calls a disability-adjusted life year, and what the site
  calls a year of healthy life lost.
- **The list is a tree.** A cause with others filed under it is their sum. The 181 causes with
  nothing under them add up to all causes.
- **The year is 2019**, the nearest to the accounts' 2017 that the Organization publishes and that
  is not a year of the pandemic.
- **The licence differs from the rest of the data here.** It allows copying and adapting with
  credit, not for commercial use, and asks that adaptations carry the same licence.
