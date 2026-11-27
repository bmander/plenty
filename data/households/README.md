# Households: their time and their spending

Inputs to the terms of the account that concern households (`plenty/site.py`): the unpaid work
done at home, and how the poorest fifth of households divide their spending among the needs.
Extracted with `scripts/00_extract_households.py`; rows and columns are selected and no values
are changed. Downloaded 2026-11-27.

| file | source | what is kept | licence |
|---|---|---|---|
| `time_use_2017.csv` | U.S. Bureau of Labor Statistics, American Time Use Survey, 2017, [Table A-1](https://www.bls.gov/tus/tables/a1_2017.pdf), time spent in detailed primary activities | Each activity's average hours a day for the civilian population of 15 and over, both sexes, in the table's order. An estimate the table prints as approximately zero is 0. | U.S. government work, public domain |
| `spending_quintiles_2017.csv` | U.S. Bureau of Labor Statistics, Consumer Expenditure Survey, 2017, [Table 1101](https://www.bls.gov/cex/tables/calendar-year/mean-item-share-average-standard-error/cu-income-quintiles-before-taxes-2017.xlsx), quintiles of income before taxes | The mean a year for all consumer units and for each fifth by income, for every item of expenditure, with the number of consumer units and the people and children in one. Shares and standard errors are left out. | U.S. government work, public domain |

## Notes

- **A primary activity** is a person's main activity at the time. Anything done alongside it,
  such as minding a child while cooking, is not counted.
- **The time-use averages are for people of 15 and over.** The account multiplies them by the
  number of adults the spending survey counts (people less children under 18), so it leaves out
  the unpaid work of those aged 15 to 17.
- **The spending survey counts what households pay themselves.** What governments pay for them
  is not in it: public schools, most of public health insurance, police, fire and courts.
- **Which activities are unpaid work, and which paid occupation does each**, is judgment, in
  `config/unpaid_work.csv`. Which item of spending belongs to which need is in
  `config/spending_needs.csv`.
