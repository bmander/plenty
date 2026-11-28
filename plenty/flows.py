"""Where today's value flows: each need dollar, traced to the capabilities of the taxonomy.

    need dollar -> sectors      the input-output model: sector j's share of the value added
                                embodied in the need (analysis.run)
                -> occupations  the occupation mix of the sector's wage bill (OEWS)
                -> capabilities the occupation's listed software (O*NET), each product placed in
                                the taxonomy capabilities it is an example of

    theta[o, k] = sum over products p that o lists, of 1 / (capabilities p belongs to),
                  for p in k, divided by all products o lists
    work[j, k]  = sum_o wagebill[j, o] theta[o, k] / sum_o wagebill[j, o]
    flow[k]     = sum_j value_added_share[j] * work[j, k]

The flow is conserved: every step splits what it receives, so the flows of all capabilities
and what could not be attributed add up to the need dollar. It measures where today's work
goes, not how much a capability matters: every listed product counts equally, and a sector's
whole value added (capital's share included) is split the way its payroll is.

The distinctive variant splits each occupation's attributed share among its capabilities in
proportion to products x specificity, where specificity is log(occupations / occupations that
list anything in the capability). Tools every occupation lists then take little, and what an
occupation alone uses takes more. The total attributed per occupation is unchanged.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from . import model as M, analysis as A, occupations as O

TAXONOMY = M.ROOT / "taxonomy"


def listings() -> pd.DataFrame:
    """Distinct (soc, product): O*NET software lists pooled over the detailed occupations
    under each 6-digit SOC code."""
    sw = pd.read_csv(O.OCC / "onet_software_skills.csv").fillna("")
    return pd.DataFrame({"soc": O.soc6(sw["O*NET-SOC Code"]), "product": sw["Workplace Example"]}).drop_duplicates()


def product_capabilities() -> pd.DataFrame:
    """(product, capability, weight): the capabilities each O*NET product is an example of in
    the taxonomy. weight is 1 / (number of capabilities), so a product counts once in all."""
    seed = pd.read_csv(TAXONOMY / "products_seed.csv")
    pc = seed.assign(capability=seed.task.str.split(".").str[:2].str.join("."))[["product", "capability"]].drop_duplicates()
    return pc.assign(weight=1 / pc.groupby("product").capability.transform("size"))


def capabilities() -> list[str]:
    t = pd.read_csv(TAXONOMY / "capabilities.csv", dtype=str)
    return list(t.id[t.level == "1"])


def occupation_shares(ls: pd.DataFrame, pc: pd.DataFrame, caps: list[str], distinctive: bool = False) -> pd.DataFrame:
    """theta: SOC x capability, the share of the occupation's listed products in each
    capability. Rows sum to the share of its products the taxonomy places (at most 1)."""
    listed = ls.groupby("soc").size()
    n = (ls.merge(pc, on="product").groupby(["soc", "capability"]).weight.sum().unstack(fill_value=0.0)
         .reindex(index=listed.index, columns=caps, fill_value=0.0))
    theta = n.div(listed, axis=0)
    if not distinctive:
        return theta
    specificity = np.log(len(n) / (n > 0).sum().clip(lower=1))
    w = n * specificity
    split = w.div(w.sum(axis=1).replace(0, np.nan), axis=0)
    # an occupation whose capabilities are all listed by every occupation keeps the plain split
    return split.mul(theta.sum(axis=1), axis=0).fillna(theta)


def sector_work(commodities: list[str], theta: pd.DataFrame) -> pd.DataFrame:
    """work: commodity x capability, the share of the sector's wage bill spent with each
    capability, with provenance columns (occupations.shares, government and farms by stand-in)."""
    return O.shares(commodities, theta, agg="mean", use_proxies=True)


def need_value_added(m: M.Model, r: A.Result) -> pd.DataFrame:
    """Commodity x need: each sector's share of the value added embodied in the need (columns
    sum to 1). Its mean over needs is sectors.value_added_share_equal."""
    va = r.sector_by_need.mul(A.value_added_share(m), axis=0)
    return va / va.sum()


def flow(vn: pd.DataFrame, work: pd.DataFrame, caps: list[str]) -> tuple[pd.Series, pd.DataFrame, pd.DataFrame]:
    """(flow by capability, capability x need, commodity x capability terms).

    terms[j, k] = mean over needs of vn[j, n] * work[j, k]; flow is their column sum and also
    the mean of the per-need flows."""
    w = work[caps].astype(float).fillna(0.0)
    by_need = w.T @ vn
    terms = w.mul(vn.mean(axis=1), axis=0)
    return terms.sum(), by_need, terms


def occupation_value(commodities: list[str], share: pd.Series) -> pd.Series:
    """OEWS occupation code -> share of the basket's value added earned in it: the sectors'
    value-added shares passed through their wage mix."""
    W, _ = O.wage_mix(commodities, use_proxies=True)
    mix = W.div(W.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    return mix.mul(share.reindex(mix.index).fillna(0.0), axis=0).sum()


def unattributed(vn: pd.DataFrame, work: pd.DataFrame, caps: list[str]) -> dict[str, float]:
    """Where the rest of the need dollar is: sectors with no occupational data, and work the
    chain could not place (occupations with no software list, products not in the taxonomy)."""
    share = vn.mean(axis=1)
    measured = work.source.astype(str).str.startswith("oews")
    placed = work[caps].astype(float).fillna(0.0).sum(axis=1)
    return {"flowed": float((share * placed).sum()),
            "sectors_without_occupation_data": float(share[~measured].sum()),
            "work_not_placed": float((share[measured] * (1 - placed[measured])).sum())}
