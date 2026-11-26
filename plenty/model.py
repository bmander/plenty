"""Leontief model from BEA 2017 detail Make/Use tables, with capital formation endogenized.

Conventions
-----------
V : Make, industry x commodity          U : Use, commodity x industry
g : industry output = V 1               q : commodity output = V' 1
B = (U + K) diag(g)^-1   commodity inputs (incl. capital goods K) per $ of industry output
D = V diag(q)^-1         market shares (industry-technology assumption)
A = B D                  commodity x commodity direct requirements
L = (I - A)^-1           total requirements: $ of commodity j per $ of final demand for commodity i

Imports are left inside U, so A describes the technology needed regardless of where it runs
(imports are assumed to be made with US technology).
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
BEA = ROOT / "data" / "bea"
CONFIG = ROOT / "config"

HOUSING = ["531HSO", "531HST"]
FED_DEFENSE = ["S00500"]
FED_NONDEF = ["S00600", "S00101", "S00102", "491000"]
STATE_LOCAL = ["GSLGE", "GSLGH", "GSLGO", "S00201", "S00202", "S00203"]
GOVERNMENT = FED_DEFENSE + FED_NONDEF + STATE_LOCAL
VA_ROWS = ["V00100", "V00200", "V00300"]

CAPITAL_COLUMNS = {
    "private": ["F02E00", "F02N00", "F02S00"],
    "residential": ["F02R00"],
    "fed_defense": ["F06E00", "F06N00", "F06S00"],
    "fed_nondefense": ["F07E00", "F07N00", "F07S00"],
    "state_local": ["F10E00", "F10N00", "F10S00"],
}
INVESTMENT_COLUMNS = [c for cols in CAPITAL_COLUMNS.values() for c in cols]


@dataclass
class Tables:
    U: pd.DataFrame          # commodity x industry, $M
    V: pd.DataFrame          # industry x commodity, $M
    F: pd.DataFrame          # commodity x final-demand column, $M
    VA: pd.DataFrame         # value-added row x industry, $M
    names: pd.Series         # commodity code -> name
    ind_names: pd.Series     # industry code -> name

    @property
    def commodities(self): return list(self.U.index)
    @property
    def industries(self): return list(self.U.columns)
    @property
    def q(self): return self.V.sum(axis=0)
    @property
    def g(self): return self.V.sum(axis=1)


def load_tables() -> Tables:
    use = pd.read_csv(BEA / "Detail_Use_2017_PRO_AfterRedef_17sch.csv", index_col=0).fillna(0.0)
    make = pd.read_csv(BEA / "Detail_Make_2017_AfterRedef_17sch.csv", index_col=0).fillna(0.0)
    ind = [i for i in make.index if not i.startswith("T")]
    com = [c for c in make.columns if not c.startswith("T")]
    fd = [c for c in use.columns if c.startswith("F")]
    cn = pd.read_csv(BEA / "Detail_CommodityCodeName_2017.csv", index_col=0)
    inn = pd.read_csv(BEA / "Detail_IndustryCodeName_2017.csv", index_col=0)
    names = pd.Series(cn.iloc[:, 1].values, index=cn.iloc[:, 0].values).reindex(com)
    ind_names = pd.Series(inn.iloc[:, 1].values, index=inn.iloc[:, 0].values).reindex(ind)
    return Tables(U=use.loc[com, ind], V=make.loc[ind, com], F=use.loc[com, fd],
                  VA=use.loc[VA_ROWS, ind], names=names, ind_names=ind_names)


def _match(codes, prefixes):
    return [c for c in codes if any(c.startswith(p) for p in prefixes)]


# The one pairing that holds whether or not config/capital_allocation.csv is used.
HOUSING_RULE = {"group": "residential", "commodity_prefixes": "233412", "user_industry_prefixes": "531HST",
                "note": "Multifamily residential structures -> tenant-occupied housing"}


@dataclass
class Capital:
    """How investment is placed on industries: K[c, j] = investment[c, group of j] * shares[c, j]."""
    investment: pd.DataFrame     # commodity x investor group, $M bought as investment in 2017
    shares: pd.DataFrame         # commodity x industry: the share of its group's investment in c placed on j
    weight: pd.Series            # industry -> what industries of a group share by, $M
    group: pd.Series             # industry -> its investor group (a key of CAPITAL_COLUMNS)
    steps: list[dict]            # what was placed where, in order: group, note ("" for the rest), commodities, users

    @property
    def K(self) -> pd.DataFrame:
        return self.shares * self.investment[self.group[self.shares.columns]].values


def capital_allocation(t: Tables, use_rules: bool = True) -> Capital:
    """BEA publishes investment by commodity and by kind of investor, but not by purchasing
    industry at this level, so each investor group's purchases of a capital good are spread over
    that group's industries:
      * a capital good with an evident user (config/capital_allocation.csv) goes to that user set
      * everything else goes to all the group's industries
    Within a set, private and housing industries share by gross operating surplus (a proxy for
    capital income) and government industries by output. A commodity a group did not invest in
    has no shares in that group.
    """
    ind, com = t.industries, t.commodities
    members = {"private": [i for i in ind if i not in HOUSING + GOVERNMENT], "residential": HOUSING,
               "fed_defense": FED_DEFENSE, "fed_nondefense": FED_NONDEF, "state_local": STATE_LOCAL}
    group = pd.Series({i: h for h, users in members.items() for i in users}).reindex(ind)
    gos = t.VA.loc["V00300"].clip(lower=0.0)
    weight = gos.where(group.isin(["private", "residential"]), t.g)
    rules = pd.concat([pd.read_csv(CONFIG / "capital_allocation.csv").iloc[:None if use_rules else 0],
                       pd.DataFrame([HOUSING_RULE])], ignore_index=True)
    investment = pd.DataFrame({h: t.F[cols].sum(axis=1) for h, cols in CAPITAL_COLUMNS.items()})
    shares = pd.DataFrame(0.0, index=com, columns=ind)
    steps = []

    def place(h, note, cs, users):
        w = weight.reindex(users).fillna(0.0)
        if w.sum() <= 0:
            raise ValueError(f"no weight for users {users[:5]}")
        shares.loc[cs, users] = (w / w.sum()).values
        steps.append({"group": h, "note": note, "commodities": cs, "users": users})

    for h, eligible in members.items():
        inv = investment[h]
        todo = list(inv.index[inv != 0])   # negatives (sales of used equipment, scrap) are kept so accounts balance
        for r in rules[rules.group == h].itertuples():
            cs = _match(todo, r.commodity_prefixes.split(";"))
            if cs:
                place(h, r.note, cs, _match(eligible, r.user_industry_prefixes.split(";")))
                todo = [c for c in todo if c not in cs]
        place(h, "", todo, eligible)
    return Capital(investment=investment, shares=shares, weight=weight, group=group, steps=steps)


def capital_matrix(t: Tables, use_rules: bool = True) -> pd.DataFrame:
    """K[c, j]: $M of capital good c bought by industry j in 2017 (allocated, not observed)."""
    return capital_allocation(t, use_rules).K


def market_shares(t: Tables) -> np.ndarray:
    """D[i, c]: the share of commodity c's output made by industry i."""
    q = t.q.values
    return t.V.values / np.where(q > 0, q, np.inf)[None, :]   # commodities nobody makes are dead ends


@dataclass
class Model:
    t: Tables
    A: pd.DataFrame
    L: pd.DataFrame
    K: pd.DataFrame | None


def build(endogenize_capital: bool = True, capital_rules: bool = True) -> Model:
    t = load_tables()
    g, q = t.g, t.q
    K = capital_matrix(t, capital_rules) if endogenize_capital else None
    inputs = t.U + K if K is not None else t.U
    B = inputs.values / g.values[None, :]
    A = B @ market_shares(t)
    L = np.linalg.inv(np.eye(len(q)) - A)
    com = t.commodities
    return Model(t=t, A=pd.DataFrame(A, index=com, columns=com),
                 L=pd.DataFrame(L, index=com, columns=com), K=K)
