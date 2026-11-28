# Households: their time and their spending

Inputs to the terms of the account that concern households (`plenty/site.py`): the unpaid work
done at home, and how the poorest fifth of households divide their spending among the needs.
Extracted with `scripts/00_extract_households.py`; rows and columns are selected and no values
are changed. Downloaded 2026-11-27.

| file | source | what is kept | licence |
|---|---|---|---|
| `time_use_2017.csv` | U.S. Bureau of Labor Statistics, American Time Use Survey, 2017, [Table A-1](https://www.bls.gov/tus/tables/a1_2017.pdf), time spent in detailed primary activities | Each activity's average hours a day for the civilian population of 15 and over, both sexes, in the table's order. An estimate the table prints as approximately zero is 0. | U.S. government work, public domain |
| `spending_quintiles_2017.csv` | U.S. Bureau of Labor Statistics, Consumer Expenditure Survey, 2017, [Table 1101](https://www.bls.gov/cex/tables/calendar-year/mean-item-share-average-standard-error/cu-income-quintiles-before-taxes-2017.xlsx), quintiles of income before taxes | The mean a year for all consumer units and for each fifth by income, for every item of expenditure, with the number of consumer units and the people and children in one. Shares and standard errors are left out. | U.S. government work, public domain |
| `wellbeing_by_activity.csv` | U.S. Bureau of Labor Statistics, American Time Use Survey, [Well-Being Module](https://www.bls.gov/tus/modules/wbdatafiles.htm), 2010, 2012, 2013 and 2021: the module's activity files (`wbact_1013.zip`, `wbact-2021.zip`) joined to the survey's activity files for those years (`atusact_2010.zip`, `atusact_2012.zip`, `atusact_2013.zip`, `atusact-2021.zip`). Extracted with `scripts/00_extract_wellbeing.py`, downloaded 2026-11-27 | For each six-digit activity code that was rated: the number of ratings, its share of the rated time, the mean of each of six feelings (0 to 6), and the share of the time that was unpleasant; then the activity on one scale from 0 to 10 (`points`), the share of the time with a bad feeling at 5 or 6 (`severe`), and the points it was rated below the same person's other time that was not work (`below_rest`, over `compared` ratings making up `compared_time` of the rated time). Computed from the microdata, with the module's activity weights. | U.S. government work, public domain |

## Notes

- **Unpleasant time** is time in an activity during which the respondent rated pain, sadness or
  stress above happiness, the measure of Kahneman and Krueger's national time accounting. Each
  respondent rated three of the day's activities. Sleeping, grooming and private activities were
  not rated.
- **Points** put a rated activity on one scale: happiness less the mean of pain, sadness and
  stress, which runs from -6 to 6, moved and stretched to run from 0 to 10. Which feelings go
  into it, and that they count equally, is judgment.
- **Below the rest** compares a rating with the same person's other rated time that was not
  work: not working at a job (code 0501) and not a kind of unpaid work named in
  `config/unpaid_work.csv`. Comparing within a person keeps those who rate everything low, or who
  have no job, from moving the figure. A respondent with no other such time is left out, which
  is about a fifth of the ratings. The extract reads `config/unpaid_work.csv`, so it is run
  again when the kinds of unpaid work change.
- **The wellbeing years are pooled.** 2021 was collected from March to December, during the
  pandemic. The 2010 to 2013 files use the weight the Bureau adjusted for an error in how
  activities were selected (`WUFNACTWTC`).
- **Which survey codes each kind of unpaid work is**, is in `config/unpaid_work.csv`. The hours
  a day under those codes agree with Table A-1's.

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
