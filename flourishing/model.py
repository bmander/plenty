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


def capital_matrix(t: Tables, use_rules: bool = True) -> pd.DataFrame:
    """K[c, j]: $M of capital good c bought by industry j in 2017 (allocated, not observed).

    BEA publishes investment by commodity but not by purchasing industry at this level,
    so each investment column is spread over plausible buyers:
      * capital goods with an evident user (config/capital_allocation.csv) go to that user set
      * everything else goes to all eligible industries
    Within a set, private industries share by gross operating surplus (a proxy for capital
    income) and government industries by output.
    """
    ind, com = t.industries, t.commodities
    gos = t.VA.loc["V00300"].clip(lower=0.0)
    g = t.g
    rules = pd.read_csv(CONFIG / "capital_allocation.csv")
    K = pd.DataFrame(0.0, index=com, columns=ind)

    def spread(amounts: pd.Series, users: list[str], weight: pd.Series):
        w = weight.reindex(users).fillna(0.0)
        if w.sum() <= 0:
            raise ValueError(f"no weight for users {users[:5]}")
        K.loc[amounts.index, users] += np.outer(amounts.values, (w / w.sum()).values)

    def allocate(group, columns, eligible, weight):
        inv = t.F[columns].sum(axis=1)
        inv = inv[inv != 0]   # negatives (sales of used equipment, scrap) are kept so accounts balance
        done = set()
        for _, r in rules[(rules.group == group) & use_rules].iterrows():
            cs = [c for c in _match(inv.index, r.commodity_prefixes.split(";")) if c not in done]
            users = _match(eligible, r.user_industry_prefixes.split(";"))
            if cs:
                spread(inv[cs], users, weight)
                done.update(cs)
        rest = [c for c in inv.index if c not in done]
        spread(inv[rest], eligible, weight)

    private = [i for i in ind if i not in HOUSING + GOVERNMENT]
    allocate("private", CAPITAL_COLUMNS["private"], private, gos)
    # Residential investment is the capital of the housing industries. Multifamily -> tenant.
    res = t.F[CAPITAL_COLUMNS["residential"]].sum(axis=1)
    res = res[res != 0]
    multi = [c for c in res.index if c == "233412"]
    spread(res[multi], ["531HST"], gos)
    spread(res.drop(multi), HOUSING, gos)
    allocate("fed_defense", CAPITAL_COLUMNS["fed_defense"], FED_DEFENSE, g)
    allocate("fed_nondefense", CAPITAL_COLUMNS["fed_nondefense"], FED_NONDEF, g)
    allocate("state_local", CAPITAL_COLUMNS["state_local"], STATE_LOCAL, g)
    return K


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
    qsafe = np.where(q.values > 0, q.values, np.inf)   # commodities nobody makes are dead ends
    D = t.V.values / qsafe[None, :]
    A = B @ D
    L = np.linalg.inv(np.eye(len(q)) - A)
    com = t.commodities
    return Model(t=t, A=pd.DataFrame(A, index=com, columns=com),
                 L=pd.DataFrame(L, index=com, columns=com), K=K)
