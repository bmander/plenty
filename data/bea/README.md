# BEA 2017 detail input-output tables

These CSVs are the U.S. Bureau of Economic Analysis 2017 benchmark Make and Use tables
(after redefinitions, producer prices, 402 commodities x 402 industries, $ millions), plus
their code/name lists. BEA data is a U.S. government work in the public domain.

They were extracted with `scripts/00_extract_bea.py` from the `.rda` files shipped in the
U.S. EPA's [useeior](https://github.com/USEPA/useeior) package (MIT license, see
`LICENSE-useeior`), which mirrors the BEA originals at
https://www.bea.gov/industry/input-output-accounts-data. No values were changed.

# Hours worked by industry, 2016

`hours_2016.csv` has, for each of 63 industries, the hours worked in 2016 (millions, employees and
the self-employed), what labor was paid and value added (millions of dollars). It was extracted with
`scripts/00_extract_hours.py` from the underlying data of the BEA-BLS integrated industry-level
production account, 1947-2016 (`KLEMS-Research-Tables-Underlying-Data_0.xlsx`, at
https://www.bea.gov/products/integrated-industry-level-production-account-klems), downloaded
2026-11-27. Only the last year was kept and no values were changed. The Bureau calls these data
experimental. They are a U.S. government work in the public domain.

`production_account_1987_2016.csv` is from the same workbook and the same script: for each of the 63
industries and each year from 1987 to 2016, the hours worked, gross output and intermediate inputs
(millions of dollars), and the quantity index of each. `plenty/hours.py` works out from it how the
hours behind a unit of each industry's real value added have moved.
