"""Basket demand, sector weights, bottleneck measures, and capability roll-up."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd
from . import model as M

GOODS_PREFIX = ("1", "21", "3")          # farm, mining, manufacturing: goods that carry margins
GOV_CONSUMPTION = ["F06C00", "F07C00", "F10C00"]
# Share of a sector's activity taken to depend on a capability, by ordinal score.
# 3 = cannot design, run or maintain without it; 2 = important and routine; 1 = incidental.
SCORE_WEIGHT = {0: 0.0, 1: 0.1, 2: 0.3, 3: 1.0}
SCORE_WEIGHT_LINEAR = {0: 0.0, 1: 1 / 3, 2: 2 / 3, 3: 1.0}


def need_demand(t: M.Tables) -> pd.DataFrame:
    """Final demand by commodity (rows) and need (columns), $M, for every need in the config.

    Household consumption (PCE) plus government consumption. Mixed retail, wholesale and
    freight margins are split over needs in proportion to each need's share of goods PCE.
    Investment is not final demand here: it is an input (see model.capital_matrix).
    """
    basket = pd.read_csv(M.CONFIG / "basket.csv").set_index("commodity").reindex(t.commodities)
    needs = pd.read_csv(M.CONFIG / "needs.csv")
    fd = t.F["F01000"] + t.F[GOV_CONSUMPTION].sum(axis=1)
    cols = [n for n in needs.need if n not in ("margin", "none")]
    Dn = pd.DataFrame(0.0, index=t.commodities, columns=cols)
    for n in cols:
        m = basket.need == n
        Dn.loc[m, n] = fd[m]
    goods = [c for c in t.commodities if c.startswith(GOODS_PREFIX)]
    goods_by_need = Dn.loc[goods].clip(lower=0).sum()
    share = goods_by_need / goods_by_need.sum()
    for c in basket.index[basket.need == "margin"]:
        Dn.loc[c] = fd[c] * share
    return Dn


def included_needs() -> list[str]:
    needs = pd.read_csv(M.CONFIG / "needs.csv")
    return list(needs.need[needs.include == 1])


def capability_scores(t: M.Tables) -> pd.DataFrame:
    """Commodity x capability score on 0..3 (elicited per archetype, see config)."""
    arch = pd.read_csv(M.CONFIG / "sector_archetypes.csv").set_index("commodity").archetype
    caps = pd.read_csv(M.CONFIG / "archetype_capabilities.csv").set_index("archetype")
    return caps.loc[arch.reindex(t.commodities)].set_axis(t.commodities, axis=0)


def value_added_share(m: M.Model) -> pd.Series:
    """Value added per $ of commodity output (industry VA shares mixed by market share)."""
    t = m.t
    va_per_output = (t.VA.sum(axis=0) / t.g).values
    q = t.q.values
    D = t.V.values / np.where(q > 0, q, np.inf)[None, :]
    return pd.Series(va_per_output @ D, index=t.commodities)


def entropy_breadth(P: np.ndarray, axis: int) -> np.ndarray:
    """Effective number of categories: exp(Shannon entropy) of non-negative weights."""
    P = np.clip(P, 0, None)
    tot = P.sum(axis=axis, keepdims=True)
    P = P / np.where(tot > 0, tot, 1.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        h = -np.where(P > 0, P * np.log(P), 0.0).sum(axis=axis)
    return np.exp(h)


@dataclass
class Result:
    sectors: pd.DataFrame            # one row per commodity
    need_totals: pd.Series           # $M final demand per included need
    sector_by_need: pd.DataFrame     # $ of sector output per $ of need
    capabilities: pd.DataFrame       # one row per capability
    capability_by_need: pd.DataFrame # value-added-weighted capability share per need


def run(m: M.Model, reach_eps=(0.0003, 0.001, 0.003), cap_eps=(0.001, 0.01, 0.05),
        critical_score: int = 3, score_weight: dict | None = None,
        usage: pd.DataFrame | None = None) -> Result:
    """usage: optional commodity x capability share in [0, 1] (e.g. occupations.usage_matrix)
    used in place of score-weighted scores for the volume measures. Exposure and reach always
    come from the elicited scores (they are about criticality, not usage)."""
    t = m.t
    com = t.commodities
    needs = included_needs()
    Dn = need_demand(t)[needs]
    T = Dn.sum()                                   # $M per need
    L = m.L.values
    X = L @ Dn.values                              # output of j required by need n, $M
    per_dollar = X / T.values[None, :]             # $ of j per $ of need n
    v = value_added_share(m).values
    arch = pd.read_csv(M.CONFIG / "sector_archetypes.csv").set_index("commodity").archetype.reindex(com)
    basket = pd.read_csv(M.CONFIG / "basket.csv").set_index("commodity").reindex(com)

    # --- sector measures
    x_spend = X.sum(axis=1)
    domar_spend = x_spend / T.sum()                # Hulten/Cobb-Douglas end: sales share
    domar_equal = per_dollar.mean(axis=1)          # each need counts equally
    need_breadth = entropy_breadth(per_dollar, axis=1)
    Wn = Dn.values / T.values[None, :]             # final-demand shares within each need
    w_equal = Wn.mean(axis=1)                      # equal-need weight on each final commodity
    sectors = pd.DataFrame({
        "name": t.names.values, "archetype": arch.values, "consumed_as": basket.need.values,
        "output_per_basket_dollar": domar_spend,
        "output_per_need_dollar_equal": domar_equal,
        "value_added_per_basket_dollar": domar_spend * v,
        "need_breadth": need_breadth,
        "top_need": [needs[i] for i in per_dollar.argmax(axis=1)],
    }, index=pd.Index(com, name="commodity"))
    for eps in reach_eps:                          # Leontief/O-ring end: who depends on j at all
        sectors[f"reach_{eps:g}"] = (L >= eps).astype(float) @ w_equal
    sectors["product_breadth"] = entropy_breadth(L * w_equal[None, :], axis=1)
    sector_by_need = pd.DataFrame(per_dollar, index=com, columns=needs)

    # --- capability measures
    S = capability_scores(t)
    sw = score_weight or SCORE_WEIGHT
    if usage is None:
        C = S.replace(sw).values.astype(float)
    else:
        C = usage.reindex(index=com, columns=S.columns).values.astype(float)
        if np.isnan(C).any():
            raise ValueError("usage matrix is missing commodities or capabilities")
    va = X * v[:, None]                            # value added in j attributable to need n, $M
    cap_by_need = pd.DataFrame((C.T @ va) / va.sum(axis=0)[None, :], index=S.columns, columns=needs)
    caps = pd.DataFrame(index=S.columns)
    caps["weight_spending"] = (C.T @ va.sum(axis=1)) / va.sum()
    caps["weight_equal_need"] = cap_by_need.mean(axis=1)
    caps["need_breadth"] = entropy_breadth(cap_by_need.values, axis=1)
    crit = (S.values >= critical_score).astype(float)          # sectors that cannot do without k
    Mik = crit.T @ L                                           # $ through k-critical sectors per $ of final i
    for eps in cap_eps:
        caps[f"reach_{eps:g}"] = (Mik >= eps).astype(float) @ w_equal
    expo = Mik @ Wn                                            # capability x need exposure
    caps["exposure_mean"] = expo.mean(axis=1)                  # $ via k-critical sectors per $ of need
    caps["exposure_min"] = expo.min(axis=1)
    caps["least_exposed_need"] = [needs[i] for i in expo.argmin(axis=1)]
    caps["most_exposed_need"] = [needs[i] for i in expo.argmax(axis=1)]
    caps["n_critical_sectors"] = crit.sum(axis=0).astype(int)
    return Result(sectors=sectors, need_totals=T, sector_by_need=sector_by_need,
                  capabilities=caps, capability_by_need=cap_by_need)
