"""Hours of work by industry, from the BEA-BLS production account (data/bea/hours_2016.csv)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import model as M

HOURS = M.ROOT / "data" / "bea" / "hours_2016.csv"
SERIES = M.ROOT / "data" / "bea" / "production_account_1987_2016.csv"
YEAR, SINCE = 2016, 1987
PAY = "V00100"        # the Use table's row for compensation of employees
# The production account's industry for each of the benchmark's, by how the benchmark's code starts. The longest start wins.
STARTS = {
    "111": 1, "112": 1, "113": 2, "114": 2, "115": 2, "211": 3, "212": 4, "213": 5, "22": 6, "23": 7, "321": 8, "327": 9,
    "331": 10, "332": 11, "333": 12, "334": 13, "335": 14, "3361": 15, "3362": 15, "3363": 15, "336": 16, "337": 17, "339": 18,
    "311": 19, "312": 19, "313": 20, "314": 20, "315": 21, "316": 21, "322": 22, "323": 23, "324": 24, "325": 25, "326": 26,
    "42": 27, "44": 28, "45": 28, "4B": 28, "481": 29, "482": 30, "483": 31, "484": 32, "485": 33, "486": 34, "48A": 35,
    "492": 35, "493": 36, "511": 37, "512": 38, "515": 39, "517": 39, "518": 40, "519": 40, "522": 41, "52A": 41, "523": 42,
    "524": 43, "525": 44, "531": 45, "532": 46, "533": 46, "5411": 47, "5415": 48, "541": 49, "55": 50, "561": 51, "562": 52,
    "61": 53, "621": 54, "622": 55, "623": 55, "624": 56, "711": 57, "712": 57, "713": 58, "721": 59, "722": 60, "81": 61,
    "S005": 62, "S006": 62, "491": 62, "S001": 62,          # federal: general government, the postal service, other enterprises
    "GSL": 63, "S002": 63,                                  # state and local: general government and enterprises
}


def published() -> pd.DataFrame:
    """The production account's industries: name, hours worked (millions), labor's pay and value added ($M)."""
    return pd.read_csv(HOURS, index_col="industry")


def account_industry(codes) -> pd.Series:
    """The production account's industry that each of the benchmark's industries is filed under."""
    def of(code):
        starts = [s for s in STARTS if code.startswith(s)]
        if not starts:
            raise KeyError(f"no production-account industry for {code}")
        return STARTS[max(starts, key=len)]
    return pd.Series({c: of(c) for c in codes})


def industry_hours(t) -> pd.Series:
    """Millions of hours worked in each of the benchmark's industries. The hours of a production-account
    industry are divided among the benchmark industries filed under it in proportion to what each paid
    its employees, so an industry that pays nobody, such as housing, gets none."""
    under = account_industry(t.industries)
    paid = t.VA.loc[PAY, t.industries].clip(lower=0)
    share = paid / paid.groupby(under).transform("sum")
    return (published().hours_millions.reindex(under.values).values * share).rename("hours")


def still_needed() -> pd.Series:
    """For each of the production account's industries: the hours it took in YEAR for a unit of its own
    real value added, for each hour it took in SINCE. Under one, hours have been going; at one or over,
    none have. Real value added is output less intermediate inputs, each at its own prices and chained
    year by year (double deflation, with Tornqvist weights)."""
    x = pd.read_csv(SERIES).sort_values(["industry", "year"])
    by = x.groupby("industry")
    bought = (x.intermediate_musd / x.gross_output_musd).clip(0, 0.95)       # the part of output that is bought in
    mean_bought = (bought + bought.groupby(x.industry).shift()) / 2
    growth = (np.log(x.gross_output_quantity).groupby(x.industry).diff()
              - mean_bought * np.log(x.intermediate_quantity).groupby(x.industry).diff()) / (1 - mean_bought)
    real = np.exp(growth.groupby(x.industry).sum())                          # real value added in YEAR, over SINCE
    hours = by.hours_millions.last() / by.hours_millions.first()
    assert by.year.first().eq(SINCE).all() and by.year.last().eq(YEAR).all()
    return (hours / real).rename("still_needed")


def sector_still_needed(t) -> pd.Series:
    """The same for each commodity: the mean over the industries that make it, each weighted by the hours
    it puts into the commodity. Zero where no hours go into it."""
    hours = industry_hours(t)
    into = (hours / t.g).values[:, None] * t.V.values                        # industry x commodity: hours put into the commodity
    of_industry = still_needed().reindex(account_industry(t.industries).values).values
    total = into.sum(axis=0)
    return pd.Series(np.divide(of_industry @ into, total, out=np.zeros(len(total)), where=total > 0), index=t.commodities)
