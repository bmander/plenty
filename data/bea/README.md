# BEA 2017 detail input-output tables

These CSVs are the U.S. Bureau of Economic Analysis 2017 benchmark Make and Use tables
(after redefinitions, producer prices, 402 commodities x 402 industries, $ millions), plus
their code/name lists. BEA data is a U.S. government work in the public domain.

They were extracted with `scripts/00_extract_bea.py` from the `.rda` files shipped in the
U.S. EPA's [useeior](https://github.com/USEPA/useeior) package (MIT license, see
`LICENSE-useeior`), which mirrors the BEA originals at
https://www.bea.gov/industry/input-output-accounts-data. No values were changed.
