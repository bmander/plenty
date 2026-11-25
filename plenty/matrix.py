"""The model's matrices arranged for looking at: sectors in broad groups, A split into what was
bought to use up and what was bought to keep, and A summed to the groups.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from . import model as M

# (group, short label, code prefixes), in BEA's order. A sector takes the first group that matches,
# so the postal service, which BEA counts as a federal enterprise, is listed before transport.
GROUPS = [
    ("Government", "Government", ("S005", "S006", "S001", "S002", "GSLG", "491000")),
    ("Scrap, used goods and import adjustments", "Adjustments", ("S003", "S004", "S009")),
    ("Farms, forestry and fishing", "Farms", ("11",)),
    ("Mining", "Mining", ("21",)),
    ("Utilities", "Utilities", ("22",)),
    ("Construction", "Construction", ("23",)),
    ("Durable goods manufacturing", "Durable goods", ("321", "327", "33")),
    ("Nondurable goods manufacturing", "Nondurable goods", ("31", "32")),
    ("Wholesale and retail trade", "Trade", ("42", "44", "45", "4B")),
    ("Transportation and warehousing", "Transport", ("48", "49")),
    ("Information", "Information", ("51",)),
    ("Finance, insurance and real estate", "Finance, real estate", ("52", "53")),
    ("Professional and business services", "Business services", ("54", "55", "56")),
    ("Education and health care", "Education, health", ("61", "62")),
    ("Arts, lodging, food and other services", "Leisure, other", ("71", "72", "81")),
]
# the order groups are shown in: BEA's, with government and the adjustment rows last
ORDER = [g[0] for g in GROUPS[2:] + GROUPS[:2]]
SHORT = {g[0]: g[1] for g in GROUPS}


def groups(codes) -> pd.Series:
    """Sector code -> broad group."""
    def one(code):
        for name, _, prefixes in GROUPS:
            if code.startswith(prefixes):
                return name
        raise ValueError(f"no group for sector {code}")
    return pd.Series({c: one(c) for c in codes})


def ordered(codes) -> list[str]:
    """The codes sorted by group (ORDER), keeping BEA's order within a group."""
    g = groups(codes)
    return [c for name in ORDER for c in codes if g[c] == name]


def direct_parts(m: M.Model) -> tuple[pd.DataFrame, pd.DataFrame]:
    """A = purchases + capital: the part of each entry that comes from the Use table and the part
    that comes from the capital matrix. The second is zero when capital is not endogenized."""
    t, com = m.t, m.t.commodities
    D = M.market_shares(t)
    def per_dollar(X):
        return pd.DataFrame((X.values / t.g.values[None, :]) @ D, index=com, columns=com)
    purchases = per_dollar(t.U)
    return purchases, (per_dollar(m.K) if m.K is not None else purchases * 0.0)


def by_group(A: pd.DataFrame, q: pd.Series) -> pd.DataFrame:
    """A summed to groups: dollars of each group's products used per dollar of each group's output.
    Rows are added up; columns are averaged by the output of the sectors in them."""
    g = groups(A.index)
    rows = A.groupby(g).sum()
    out = (rows * q).T.groupby(g).sum().T / q.groupby(g).sum()
    return out.loc[ORDER, ORDER]
